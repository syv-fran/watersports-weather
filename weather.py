import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import astral
import astral.sun
import numpy as np
import openmeteo_requests
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots
from pydantic import TypeAdapter


@dataclass()
class Bounds:
    above: dict = field(default_factory=dict)
    below: dict = field(default_factory=dict)


@dataclass()
class Site:
    name: str
    location: tuple[float, float]
    sheltered_distance: float = 0.3
    sheltered_angles: tuple[float, float] = (0, 0)
    amber: Bounds = field(default_factory=Bounds)
    red: Bounds = field(default_factory=Bounds)
    icon: Bounds = field(default_factory=Bounds)
    timezone: str = "auto"


@dataclass()
class Constraint:
    symbol: str
    column: str


constraints = {
    "Tide": Constraint("⚓", "sea_level_height_msl"),
    "Rain": Constraint("🌧️", "rain"),
    "Waves": Constraint("🌊", "calc_wave_height"),
    "Wind": Constraint("💨", "wind_speed_10m"),
}


DEFAULT_N_DAYS = 9
EARLIEST_START_HOUR = 8
LATEST_END_HOUR = 20

# Measures is a list of columns. Each will be requested from openmeteo if source:forecast/marine.
# If type is "scatter" or "arrow-dir" they will be included in output scatterplot with params specified.
measures = {
    "sea_level_height_msl": {
        "type": "scatter",
        "name": "Tide",
        "row": 1,
        "source": "marine",
    },
    "wind_speed_10m": {
        "type": "scatter",
        "name": "Wind Speed",
        "row": 2,
        "source": "forecast",
    },
    "calc_wave_height": {
        "type": "scatter",
        "name": "Local Waves",
        "row": 4,
        "view": "standard",
        "source": "calc",
    },
    "swell_wave_height": {
        "type": "scatter",
        "name": "Swell",
        "row": 4,
        "view": "extended",
        "source": "marine",
    },
    "secondary_swell_wave_height": {
        "type": "scatter",
        "name": "Swell 2ary",
        "row": 4,
        "view": "extended",
        "source": "marine",
    },
    "wind_wave_height": {
        "type": "scatter",
        "name": "Wind Waves",
        "row": 4,
        "view": "extended",
        "source": "marine",
    },
    "wind_direction_10m": {
        "type": "arrow_dir",
        "name": "Wind Direction",
        "row": 3,
        "arg": "wind_speed_10m",
        "source": "forecast",
    },
    "rain": {
        "type": "scatter",
        "name": "Rain (mm)",
        "row": 2,
        "source": "forecast",
    },
    "temperature_2m": {
        "type": "data",
        "source": "forecast",
    },
    "wave_height": {
        "type": "data",
        "source": "marine",
    },
    "wave_direction": {
        "type": "data",
        "source": "marine",
    },
    "sea_surface_temperature": {
        "type": "data",
        "source": "marine",
    },
    "wind_wave_direction": {
        "type": "data",
        "source": "marine",
    },
    "swell_wave_direction": {
        "type": "data",
        "source": "marine",
    },
    "secondary_swell_wave_direction": {
        "type": "data",
        "source": "marine",
    },
}

urls = {
    "forecast": "https://api.open-meteo.com/v1/forecast",
    "marine": "https://marine-api.open-meteo.com/v1/marine",
}

traffic_colours = [
    [0.0, "#EF553B"],
    [0.33, "#EF553B"],  # red
    [0.33, "#FECB52"],
    [0.66, "#FECB52"],  # yellow
    [0.66, "#63DE71"],
    [1.0, "#63DE71"],  # green
]


# process_interval converts to polars dataframe the weather forecast 'params' over 'interval'
def process_interval(
    interval: Any, params: list[str], timezone_str: str
) -> pl.DataFrame | None:
    if not interval:
        return None
    timezone = ZoneInfo(timezone_str)
    start = datetime.fromtimestamp(interval.Time(), UTC).astimezone(timezone)
    end = datetime.fromtimestamp(interval.TimeEnd(), UTC).astimezone(timezone)
    freq = timedelta(seconds=interval.Interval())
    date_series = pl.datetime_range(start, end, freq, closed="left", eager=True)
    data_dict = {"time": date_series}

    for i, x in enumerate(params):
        array = interval.Variables(i).ValuesAsNumpy()
        if np.isfinite(array).any():
            data_dict[x] = array

    if len(data_dict) > 1:
        df = pl.DataFrame(data=data_dict)
        return df
    else:
        return None


def get_hourly(
    site: Site,
    measures: list[str],
    date_start: str,
    date_end: str,
    type: Literal["forecast", "marine"] = "forecast",
    model: str = "best_match",
) -> pl.DataFrame | None:
    (place_lat, place_long) = site.location
    params = {
        "latitude": place_lat,
        "longitude": place_long,
        "hourly": measures,
        "models": model,
        "start_date": date_start,
        "end_date": date_end,
        "timezone": site.timezone,
    }
    openmeteo = openmeteo_requests.Client()
    response = openmeteo.weather_api(urls[type], params=params)
    if site.timezone == "auto":
        response_timezone = response[0].Timezone()
        if not response_timezone:
            raise ValueError(
                f"Open-Meteo did not return a timezone for {site.name}"
            )
        if isinstance(response_timezone, bytes):
            response_timezone = response_timezone.decode("utf-8")
        site.timezone = response_timezone
    df = process_interval(response[0].Hourly(), measures, site.timezone)
    return df


def arrow_plot(
    fig: go.Figure,
    d: pl.DataFrame,
    angle: str,
    colourkey: str,
    row: int = 1,
    col: int = 1,
    vis: bool = True,
    colorscale: str = "Reds",
    meta: dict[str, object] | None = None,
) -> None:
    cl = d[colourkey].to_list()
    x = d["time"].to_list()
    y = np.zeros(len(d)).tolist()
    line = {"width": 1, "color": cl, "colorscale": colorscale}
    marker = {  # draw line of arrow
        "symbol": "line-ns",
        "size": 10,
        "line": line,
        "angle": d[angle],
        "color": cl,
        "colorscale": "Reds",
    }
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            marker=marker,
            visible=vis,
            showlegend=False,
            hoverinfo="skip",
            meta=meta,
        ),
        row=row,
        col=col,
    )
    marker["standoff"] = (
        6  # keep overall style of marker, change to non-centred triangle
    )
    marker["symbol"] = "triangle-down"
    marker["size"] = 5
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            marker=marker,
            visible=vis,
            showlegend=False,
            hoverinfo="skip",
            meta=meta,
        ),
        row=row,
        col=col,
    )


def local_sun_times(
    place: tuple[float, float],
    timezone_str: str,
    start_date: datetime,
    n_days: int,
) -> tuple[list[float], list[float]]:

    observer = astral.Observer(latitude=place[0], longitude=place[1])
    timezone = ZoneInfo(timezone_str)

    local_sunrise = []
    local_sunset = []

    for day_offset in range(n_days):
        sun = astral.sun.sun(
            observer,
            date=start_date + timedelta(days=day_offset),
            tzinfo=timezone,
        )
        local_sunrise.append(sun["sunrise"].hour + sun["sunrise"].minute / 60.0)
        local_sunset.append(sun["sunset"].hour + sun["sunset"].minute / 60.0)

    return local_sunrise, local_sunset


def blocking_shape(
    x0: float,
    x1: float,
    y_bottom: float,
    y_top: float,
    fill: float = 0.9,
) -> dict[str, object]:
    return {
        "type": "rect",
        "xref": "x1",
        "yref": "y",
        "x0": x0,
        "x1": x1,
        "y0": y_bottom,
        "y1": y_top,
        "fillcolor": f"rgba(255,255,255,{fill})",
        "line": {"width": 0},
        "layer": "above",
    }


def block_out_night(
    sunrise: list[float],
    sunset: list[float],
    start_hour: int,
    end_hour: int,
    n_days: int,
) -> list[dict[str, object]]:
    tides_shapes: list[dict[str, object]] = []
    for day_idx in range(n_days):
        y_bottom = day_idx - 0.5
        y_top = day_idx + 0.5

        if sunrise[day_idx] > start_hour:
            tides_shapes.append(
                blocking_shape(
                    -0.5,
                    min(sunrise[day_idx] - start_hour, end_hour - start_hour) + 0.5,
                    y_bottom,
                    y_top,
                )
            )
        if sunset[day_idx] < end_hour + 1:
            tides_shapes.append(
                blocking_shape(
                    max(sunset[day_idx] - start_hour, 0) - 0.5,
                    (end_hour - start_hour) + 0.5,
                    y_bottom,
                    y_top,
                )
            )
    return tides_shapes


def calc_limit(
    direction: Literal["min", "max"],
    df: pl.DataFrame,
    columns: str | list[str],
    scale: float = 1.10,
    round: bool = False,
) -> int | float:

    if direction == "max" and isinstance(columns, str):
        limit_value = df[columns].max()
    elif direction == "min" and isinstance(columns, str):
        limit_value = df[columns].min()
    elif direction == "max":
        limit_value = df.select(pl.max_horizontal(columns)).max().item()
    else:
        limit_value = df.select(pl.min_horizontal(columns)).min().item()

    assert isinstance(limit_value, (int, float)), f"No numbers in {columns}"

    adjusted_limit = limit_value * scale
    if not round:
        return adjusted_limit
    return (
        math.ceil(adjusted_limit) if direction == "max" else math.floor(adjusted_limit)
    )


def get_temperature_stripes(
    n_days: int, xref: str, lowbound: float, upbound: float
) -> list[dict[str, object]]:
    met_office_zones = [
        (lowbound, -5, "#1e3a8a"),  # Extreme cold
        (-5, 0, "#1d4ed8"),  # Dark blue
        (0, 5, "#3b82f6"),  # Medium blue
        (5, 12, "#93c5fd"),  # Light pastel blue
        (12, 16, "#a7f3d0"),  # Cool mint green
        (16, 20, "#22c55e"),  # Standard green
        (20, 24, "#fde047"),  # Pale yellow
        (24, 28, "#eab308"),  # Warm amber/yellow
        (28, 33, "#f97316"),  # Orange
        (33, 38, "#ef4444"),  # Red
        (38, upbound, "#991b1b"),  # Extreme heat
    ]
    return [
        {
            "x0": z_min,
            "x1": z_max,
            "y0": -0.5,
            "y1": n_days - 0.5,
            "xref": xref,
            "fillcolor": zone_color,
            "opacity": 0.5,
            "layer": "below",
            "line_width": 0,
        }
        for z_min, z_max, zone_color in met_office_zones
    ]


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate html weather for today or specified date"
    )
    parser.add_argument(
        "n_days",
        nargs="?",
        default=DEFAULT_N_DAYS,
        type=int,
        help="number of forecast days",
    )
    parser.add_argument(
        "--config", type=str, default="weather.json", help="Use this JSON config file"
    )
    parser.add_argument(
        "--site", type=str, help="Use this location from config file"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write generated HTML to this file instead of standard output",
    )
    parser.add_argument(
        "date_start",
        nargs="?",
        type=lambda x: datetime.fromisoformat(x).date(),
        default=datetime.now(UTC).date(),
        help="start date as YYYY-MM-DD",
    )
    args = parser.parse_args(argv)
    return args

def to_emojis (cell:str) -> str: # Reasonably space for two symbols per cell.
        if cell=='':
            return ''
        x=cell.split(',')
        match len(x):              
            case 2:
                emojis=constraints[x[0]].symbol+constraints[x[1]].symbol
            case 1:
                emojis=constraints[x[0]].symbol
            case _:
                emojis=constraints[x[0]].symbol+"+"
        return emojis
v_to_emojis = np.vectorize(to_emojis)
 
def construct_plot_tables(
    df: pl.DataFrame,
    daily_dl: pl.DataFrame,
    n_days: int,
    tides_shapes: list,
    site_name: str,
    marine_avail: bool,
) -> go.Figure:

    temps_lowerbound = calc_limit(
        "min",
        daily_dl,
        ["sea temperature", "min temp"] if marine_avail else "min temp",
        scale=1.0,
        round=True,
    )
    temps_upperbound = calc_limit(
        "max",
        daily_dl,
        ["sea temperature", "max temp"] if marine_avail else "max temp",
        scale=1.0,
        round=True,
    )
    temps_shapes = get_temperature_stripes(
        n_days, "x2", temps_lowerbound, temps_upperbound
    )

    z_matrix = df.pivot(
        on="hour", index="day", values="status_val", aggregate_function="first"
    )
    text_matrix = df.pivot(
        on="hour", index="day", values="weather_icon", aggregate_function="first"
    )

    days = z_matrix["day"].to_list()
    hours = [col for col in z_matrix.columns if col != "day"]

    z_data = z_matrix.select(hours).to_numpy()
    text_contents = text_matrix.select(hours).to_numpy()

    emoji_contents = v_to_emojis (text_contents)

 
    table_heatmap = go.Heatmap(
        z=z_data,
        x=[f"{h}:00" for h in hours],
        y=days,
        colorscale=traffic_colours,
        zmin=0,
        zmax=2,
        showscale=False,
        xgap=3,
        ygap=3,
        text=emoji_contents,
        customdata=text_contents,
        texttemplate="%{text}",
        textfont={"size": 18, "color": "black"},
        name=site_name + " Outlook",
        hovertemplate="%{customdata}<extra></extra>",
    )

    tab_multiplier = 0.80
    tabs = make_subplots(  # Construct result, which is two side by side plots.
        rows=1,
        cols=2,
        column_widths=[tab_multiplier, 1 - tab_multiplier],
        shared_yaxes=True,
    )
    tabs.add_annotation(  # handle subtitle manually for control over position
        text="Categories",
        x=0.5,
        y=1.15,
        xref="x domain",
        yref="paper",
        showarrow=False,
        xanchor="center",
    )
    tabs.add_annotation(  # handle subtitle manually for control over position
        text="Temperatures",
        x=0.5,
        y=1.15,
        xref="x2 domain",
        yref="paper",
        showarrow=False,
        xanchor="center",
    )
    tabs.add_trace(table_heatmap, row=1, col=1)

    for key, value in constraints.items():
        if (not marine_avail) and measures[value.column]['source'] == "marine":
            continue
        symbol = value.symbol
        tabs.add_trace(  # add dummy trace for each entry to show up in legend
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"size": 0},
                name=symbol + " " + key,
                legend="legend2",
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )

    tabs.add_trace(  # Bar of min to max temperature
        go.Bar(
            y=daily_dl["day"],
            base=daily_dl["min temp"],
            x=daily_dl["max temp"] - daily_dl["min temp"],
            orientation="h",
            marker={
                "color": "rgba(30, 41, 59, 0.75)",
                "cornerradius": 5,
                "line": {"color": "#0f172a", "width": 1},
            },
            name="Air",
            hovertemplate="<b>Date:</b> %{y}<br>Max: %{customdata:.1f}°C<br>Min: %{base:.1f}°C<extra></extra>",
            customdata=np.stack([daily_dl["max temp"]], axis=-1),
        ),
        row=1,
        col=2,
    )

    tabs.add_trace(  # Spot in temperature bar showing mean
        go.Scatter(
            x=daily_dl["mean temperature"],
            y=daily_dl["day"],
            mode="markers",
            marker={
                "color": "#ffffff",
                "size": 7,
                "line": {"color": "#0f172a", "width": 1.5},
            },
            name="Avg",
            hovertemplate="Date: %{y}<br>Mean: %{x:.1f}°C<extra></extra>",
        ),
        row=1,
        col=2,
    )

    if marine_avail:
        tabs.add_trace(
            go.Scatter(
                x=daily_dl["sea temperature"],
                y=daily_dl["day"],
                mode="lines+markers",
                line={"color": "#06b6d4", "width": 3, "dash": "solid"},
                marker={"size": 4, "color": "#0891b2"},
                name="Sea",
                hovertemplate="Date: %{y}<br>Sea Temp: %{x:.1f}°C<extra></extra>",
            ),
            row=1,
            col=2,
        )

    tabs.update_layout(
        height=n_days * 32 + 100,
        xaxis2={
            "range": [temps_lowerbound, temps_upperbound],
            "gridcolor": "rgba(255,255,255,0.4)",
        },
        yaxis1={"autorange": "reversed", "type": "category", "side": "right"},
        plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.35,
        dragmode=False,
        margin={"l": 0, "r": 0, "t": 50, "b": 4},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.01,
            "xanchor": "right",
            "xref": "paper",
            "x": 1.0,
        },
        legend2={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.01,
            "xanchor": "left",
            "xref": "paper",
            "x": 0.0,
        },
        shapes=tides_shapes + temps_shapes,
    )
    return tabs


def add_daily_traces(fig, day_d: pl.DataFrame, i, marine_avail: bool):
    for m, val in measures.items():
        if val["type"] == "data":
            continue
        if (m not in day_d.columns) or (
            not marine_avail and val["source"] == "marine"
        ):
            continue
        if not marine_avail and val.get("view") == "extended":
            continue
        if m == "rain" and not day_d["rain"].fill_null(0).gt(0).any():
            continue
        view = val.get("view", "both")
        meta = {
            "day_index": i,
            "standard_visible": view != "extended",
            "extended_visible": view != "standard",
        }
        vis = i == 0 and meta["standard_visible"]
        row = val["row"] if marine_avail else val["row"] - 1
        if val["type"] == "scatter":
            fig.add_trace(
                go.Scatter(
                    x=day_d["time"],
                    y=day_d[m],
                    name=val["name"],
                    legendgroup=val["name"],
                    visible=vis,
                    meta=meta,
                    hovertemplate=(
                        "Rain: %{y:.1f} mm<extra></extra>" if m == "rain" else None
                    ),
                ),
                row=row,
                col=1,
            )
        elif val["type"] == "arrow_dir":
            arrow_plot(fig, day_d, m, val["arg"], row=row, vis=vis, meta=meta)


def construct_plot_daily(df: pl.DataFrame, marine_avail: bool = True) -> go.Figure:
    unique_days = df["day"].unique(maintain_order=True).to_list()
    if marine_avail:
        global_tide_min = calc_limit("min", df, "sea_level_height_msl")
        global_tide_max = calc_limit("max", df, "sea_level_height_msl")
    rain_present = "rain" in df.columns and df["rain"].is_not_null().any()
    global_wind_rain_limit = calc_limit(
        "max", df, ["wind_speed_10m", "rain"] if rain_present else "wind_speed_10m"
    )
    wave_columns = (
        ["calc_wave_height", "swell_wave_height", "wind_wave_height"]
        if marine_avail
        else ["calc_wave_height"]
    )
    global_wave_limit = calc_limit("max", df, wave_columns)

    n_rows = 4 if marine_avail else 3
    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.01,
        row_heights=[0.20, 0.37, 0.06, 0.37] if marine_avail else [0.4625, 0.075, 0.4625],
    )

    for i, day in enumerate(unique_days):
        day_d = df.filter(pl.col("day") == day)
        add_daily_traces(fig, day_d, i, marine_avail)

    layout: dict[str, Any] = {
        "dragmode": False,
        "margin": {"t": 20, "b": 10},
        "template": "plotly_white",
        "hovermode": "x unified",
    }
    wind_rain_layout = {
        "range": [0, global_wind_rain_limit],
        "ticksuffix": " km/h",
    }
    wave_layout = {"range": [0, global_wave_limit], "ticksuffix": " m"}

    if marine_avail:
        tide_layout = {
        "range": [global_tide_min, global_tide_max],
        "ticksuffix": " m",
        }
        layout["yaxis"] = tide_layout
        layout["yaxis2"] = wind_rain_layout
        fig.update_yaxes(visible=False, row=3, col=1)
        layout["yaxis4"] = wave_layout

    else:
        layout["yaxis"] = wind_rain_layout
        fig.update_yaxes(visible=False, row=2, col=1)
        layout["yaxis3"] = wave_layout

    fig.update_layout(**layout)
    return fig


def render_html(
    site_figures: list[tuple[Site, go.Figure, go.Figure, bool]],
    date_start: str,
    n_days: int,
):
    choose_sites: bool = len(site_figures) > 1
    base_config = {
        "scrollZoom": False,
        "displaylogo": False,
        "displayModeBar": False,
        "doubleClickDelay": 1000,
        "responsive": True,
    }
    day_options_html = ""
    for i in range(n_days):
        full_day = datetime.fromisoformat(date_start).date() + timedelta(days=i)
        title = full_day.strftime("%A %d %B %y View")
        day_options_html += f'<option value="view_{i}">{title}</option>\n'

    site_options_html = ""
    site_views_html = ""

    for i, (site, grid, fig, marine_avail) in enumerate(site_figures):
        site_options_html += f'<option value="{i}">{site.name}</option>\n'
        when_generated = datetime.now(ZoneInfo(site.timezone)).strftime(
            "%Y-%B-%d %H:%M %Z"
        )
        extended_control_html = (
            f"""
                <label class="extended-label">
                    <input id="extended-view-{i}" type="checkbox" onchange="triggerExtendedUpdate({i}, this.checked)">
                    Extended view
                </label>
            """
            if marine_avail
            else ""
        )
        site_views_html += f"""
        <section class="site-view{" active" if i == 0 else ""}" id="site-{i}">
            {grid.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False, div_id=f"table-heatmap-{i}", config=base_config)}
            <div class="day-dropdown-box">
                <select id="day-{i}" onchange="triggerDayUpdate({i}, this.value)">
                    {day_options_html}
                </select>
                {extended_control_html}
            </div>
            {fig.to_html(full_html=False, include_plotlyjs=False, div_id=f"my-sel-{i}", config=base_config)}
            <small class="generated-at">Generated at {when_generated}</small>
        </section>
        """
    site_selector_html = (
        f'<select id="site-navigator" onchange="triggerSiteUpdate(this.value)">{site_options_html}</select>'
        if choose_sites
        else ""
    )
    page_title = (
        f"{site_selector_html}" if choose_sites else f"{site_figures[0][0].name}"
    )
    site_select_js = (
        'document.getElementById("site-navigator").value = index;'
        if choose_sites
        else ""
    )
    day_titles = {
        f"view_{i}": (
            datetime.fromisoformat(date_start).date() + timedelta(days=i)
        ).strftime("%A %d %B %y")
        for i in range(n_days)
    }
    template = Path(__file__).with_name("weather_template.html").read_text()
    replacements = {
        "@@PAGE_TITLE@@": page_title,
        "@@SITE_VIEWS@@": site_views_html,
        "@@DAY_LABELS@@": json.dumps(
            {
                f"view_{i}": (
                    datetime.fromisoformat(date_start).date() + timedelta(days=i)
                ).strftime("%a %d")
                for i in range(n_days)
            }
        ),
        "@@DAY_TITLES@@": json.dumps(day_titles),
        "@@SITE_COUNT@@": str(len(site_figures)),
        "@@SITE_SELECT_JS@@": site_select_js,
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def build_wave_expr(angle_h, angle_l, marine_avail: bool = True):
    if not marine_avail:
        return pl.col("lower_wind_bound")
    return (
        pl.when(pl.col("swell_wave_direction").is_between(angle_l, angle_h))
        .then(pl.col("swell_wave_height") ** 2)
        .otherwise(0)
        + pl.when(pl.col("secondary_swell_wave_direction").is_between(angle_l, angle_h))
        .then(pl.col("secondary_swell_wave_height") ** 2)
        .otherwise(0)
        + pl.when(pl.col("wind_wave_direction").is_between(angle_l, angle_h))
        .then(pl.col("wind_wave_height") ** 2)
        .otherwise(pl.col("lower_wind_bound") ** 2)
    ).sqrt()


def build_constraints_exprs(site, constraints):
    # Build polars expressions for bounds and config specified in 'site' for traffic light colour and symbol.
    # constraints have been pre-filtered so they do not refer to non-existent columns
    expr = pl.when(pl.lit(False)).then(2)
    # False expr will never happen but makes 'otherwise' always work at end
    for x, val in site.red.above.items():
        expr = expr.when(pl.col(constraints[x].column) > val).then(0)
    for x, val in site.red.below.items():
        expr = expr.when(pl.col(constraints[x].column) <= val).then(0)
    for x, val in site.amber.above.items():
        expr = expr.when(pl.col(constraints[x].column) > val).then(1)
    for x, val in site.amber.below.items():
        expr = expr.when(pl.col(constraints[x].column) <= val).then(1)
    icon_exprs = []
    for x, val in site.icon.above.items():
        icon_exprs.append(
            pl.when(pl.col(constraints[x].column) > val)
            .then(pl.lit(x))
            .otherwise(None)
        )
    for x, val in site.icon.below.items():
        icon_exprs.append(
            pl.when(pl.col(constraints[x].column) <= val)
            .then(pl.lit(x))
            .otherwise(None)
        )
    i_expr = (
        pl.concat_str(icon_exprs, separator=",", ignore_nulls=True).fill_null("")
        if icon_exprs
        else pl.lit("")
    )

    return expr.otherwise(2), i_expr


def process_dataframe(df, site,marine_avail:bool):
    # Define the forecast wave height as Root Sum of Squares of waves,
    # for each swell or wind wave in the allowed direction. If wind wave isn't in that direction,
    # the sum should use the calculated wind wave in a sheltered area based on fetch provided.
    # Then add traffic-light categories based on acceptable conditions
    # and conditions to go in Icon field.
    # finally create a new 'daily' dataframe with per-day max,min,mean measures.

    # factor uses Carter formula assuming units in km and km/h .
    wind_factor = 0.004528 * math.sqrt(site.sheltered_distance)
    sheltered_angles = site.sheltered_angles if marine_avail else (None, None)
    rss = build_wave_expr(*sheltered_angles, marine_avail=marine_avail)
   # if "rain" not in df.columns:
    #    df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias("rain"))

    # Loop over all constraints provided in 'site' to form conditional expressions.
    available_constraints = (
        constraints
        if marine_avail
        else {
            key: value
            for key, value in constraints.items()
            if measures[value.column]["source"] != "marine"
        }
    )
    traffic_expr, icon_expr = build_constraints_exprs(site, available_constraints)

    df = (
        df.with_columns(
            day=pl.col("time").dt.strftime("%a %d"),
            hour=pl.col("time").dt.hour(),
            lower_wind_bound=pl.col("wind_speed_10m") * wind_factor,
        )
        .with_columns(
            calc_wave_height=rss,
        )
        .with_columns(
            status_val=traffic_expr,
            weather_icon=icon_expr,
        )
        .sort("time", descending=False)
    )
    daily_aggregations = [
        pl.col("temperature_2m").max().alias("max temp"),
        pl.col("temperature_2m").min().alias("min temp"),
        pl.col("temperature_2m").mean().alias("mean temperature"),
    ]
    if marine_avail and "sea_surface_temperature" in df.columns:
        daily_aggregations.append(
            pl.col("sea_surface_temperature").mean().alias("sea temperature")
        )
    daily = (
        df.group_by(pl.col("time").dt.date(), pl.col("day"))
        .agg(daily_aggregations)
        .sort("time")
    )
    return df, daily


def merge_site_config(
    defaults: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    merged = defaults.copy()
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_site_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_sites(args) -> list[Site]:
    try:
        config_adapter = TypeAdapter(dict[str, dict[str, Any]])
        with open(args.config, "r", encoding="utf-8") as f:
            site_configs = config_adapter.validate_json(f.read())
    except FileNotFoundError:
        sys.exit(f"Error: The config file '{args.config}' could not be found.")
    global_defaults = site_configs.get("global", {})
    merged_configs = {}
    for name, site_config in site_configs.items():
            merged= merge_site_config(global_defaults, site_config)
            if site_config.get("location"):
                merged_configs[name] = merged
    sites = TypeAdapter(dict[str, Site]).validate_python(merged_configs)
    if args.site:
        s = sites.get(args.site)
        if not s:
            sys.exit(
                f"Error: The config file '{args.config}' does not contain an entry '{args.site}'."
            )
        return [s]
    return list(sites.values())


def main(argv: list[str] | None = None) -> None:

    args = parse_cli_args(argv)
    sites = get_sites(args)
    date_start_str = args.date_start.isoformat()
    date_end_str = (args.date_start + timedelta(days=args.n_days - 1)).isoformat()
    forecast_measures = [
        col for col, measure in measures.items() if measure["source"] == "forecast"
    ]
    marine_measures = [
        col for col, measure in measures.items() if measure["source"] == "marine"
    ]
    site_figures = []
    for site in sites:
        d_a = get_hourly(
            site, forecast_measures, date_start_str, date_end_str, "forecast"
        )
        d_b = get_hourly(
            site, marine_measures, date_start_str, date_end_str, "marine"
        )
        assert d_a is not None, f"No forecast for {site.name}"
        marine_avail = d_b is not None
        if d_b is None:
            df = d_a
        else:
            df = d_a.join(d_b, on="time", how="full", coalesce=True)

        sunrise, sunset = local_sun_times(
            site.location, site.timezone, args.date_start, args.n_days
        )
        start_hour = max(EARLIEST_START_HOUR, int(min(sunrise)))
        end_hour = min(LATEST_END_HOUR, int(max(sunset)))
        df = df.filter(
            pl.col("time").dt.hour().is_between(start_hour, end_hour)
        )
        df, daily = process_dataframe(df, site,marine_avail)
        tides_shapes = block_out_night(
            sunrise, sunset, start_hour, end_hour, args.n_days
        )
        grid = construct_plot_tables(
            df, daily, args.n_days, tides_shapes, site.name, marine_avail
        )
        fig = construct_plot_daily(df, marine_avail)
        site_figures.append((site, grid, fig, marine_avail))

    output = render_html(site_figures, date_start_str, args.n_days)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
