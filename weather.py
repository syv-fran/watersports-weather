import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
    above:dict = field(default_factory=dict)
    below:dict = field(default_factory=dict)

@dataclass()
class Site:
    name:str
    location:tuple[float,float]
    sheltered_distance: float = 0.3 
    sheltered_angles: tuple[float,float] = (0,0)
    amber:Bounds =  field(default_factory=Bounds)
    red:Bounds =  field(default_factory=Bounds)
    icon:Bounds =  field(default_factory=Bounds)
    timezone:str = "Europe/London"

@dataclass()
class Constraint:
    symbol: str
    column: str

constraints = {"Tide": Constraint("⚓","sea_level_height_msl"),
               "Rain": Constraint("🌧️","rain"),
               "Waves": Constraint("🌊","calc_wave_height"), 
               "Wind": Constraint("💨","wind_speed_10m")}


DEFAULT_N_DAYS = 9
EARLIEST_START_HOUR= 8
LATEST_END_HOUR = 20

# Measures is a list of columns. Each will be requested from openmeteo if source:forecast/marine. 
# If type is "scatter" or "arrow-dir" they will be included in output scatterplot with params specified.
measures = {
    "sea_level_height_msl": {
        "type": "scatter",
        "name": "Tide",
        "row": 1,
        "visible_start": True,
        "source": "marine",
    },
    "wind_speed_10m": {
        "type": "scatter",
        "name": "Wind Speed",
        "row": 2,
        "visible_start": True,
        "source": "forecast",
    },
    "calc_wave_height": {
        "type": "scatter",
        "name": "Local Waves",
        "row": 4,
        "visible_start": True,
        "source": "calc",
    },
    "swell_wave_height": {
        "type": "scatter",
        "name": "Swell",
        "row": 4,
        "visible_start": False,
        "source": "marine",
    },
    "secondary_swell_wave_height": {
        "type": "scatter",
        "name": "Swell 2ary",
        "row": 4,
        "visible_start": False,
        "source": "marine",
    },
    "wind_wave_height": {
        "type": "scatter",
        "name": "Wind Waves",
        "row": 4,
        "visible_start": False,
        "source": "marine",
    },
    "wind_direction_10m": {
        "type": "arrow_dir",
        "name": "Wind Direction",
        "row": 3,
        "visible_start": True,
        "arg": "wind_speed_10m",
        "source": "forecast",
    },
    "rain": {
        "type": "data",
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
def process_interval(interval: Any, params: list[str]) -> pl.DataFrame | None:
    if not interval:
        return None
    start = datetime.fromtimestamp(interval.Time(), UTC)
    end = datetime.fromtimestamp(interval.TimeEnd(), UTC)
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
    place: tuple[float, float],
    measures: list[str],
    date_start: str,
    date_end: str,
    type: Literal["forecast", "marine"] = "forecast",
    model: str = "best_match",
) -> pl.DataFrame | None:
    ( place_lat, place_long) = place
    params = {
        "latitude": place_lat,
        "longitude": place_long,
        "hourly": measures,
        "models": model,
        "start_date": date_start,
        "end_date": date_end,
    }
    openmeteo = openmeteo_requests.Client()
    response = openmeteo.weather_api(urls[type], params=params)
    df = process_interval(response[0].Hourly(), measures)
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
) -> None:
    cl = d[colourkey].to_list()
    x = d["time"].to_list()
    y = np.zeros(len(d)).tolist()
    line = {"width": 1, "color": cl, "colorscale": colorscale}
    marker = { # draw line of arrow
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
        ),
        row=row,
        col=col,
    )
    marker["standoff"] = 6 # keep overall style of marker, change to non-centred triangle
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
        ),
        row=row,
        col=col,
    )


def local_sun_times(
    place: tuple[ float, float],
    timezone_str:str,
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
    x1:  float,
    y_bottom: float,
    y_top:  float,
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
                    min(sunrise[day_idx] - start_hour,end_hour - start_hour) + 0.5,
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

    assert isinstance(limit_value, (int, float)), ( f"No numbers in {columns}" )
    
    adjusted_limit = limit_value * scale
    if not round:
        return adjusted_limit
    return math.ceil(adjusted_limit) if direction == "max" else math.floor(adjusted_limit)

def get_temperature_stripes(n_days: int, xref: str, lowbound: float, upbound: float) -> list[dict[str, object]]:
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


def make_mask(day_idx: int, n_days: int, extended: bool = False) -> list[bool]:
    mask: list[bool] = []
    N_TRACES = 8
    for d in range(n_days):
        daymask = [(d == day_idx)] * N_TRACES
        if d == day_idx and extended:
            daymask[2] = False
        elif d == day_idx:
            daymask[3] = daymask[4] = daymask[5] = False
        mask.extend(daymask)
    return mask

def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace :
    parser = argparse.ArgumentParser(description="Generate html weather for today or specified date")
    parser.add_argument("n_days", nargs="?", default=DEFAULT_N_DAYS, type=int, help="number of forecast days")
    parser.add_argument("--config", type=str, default="weather.json", help="Use this JSON config file")
    parser.add_argument("--site", type=str, default="default", help="Use this location from config file")
    parser.add_argument(
        "date_start",
        nargs="?",
        type=lambda x: datetime.fromisoformat(x).date(),
        default=datetime.now(UTC).date(),
        help="start date as YYYY-MM-DD",
    )
    args = parser.parse_args(argv)
    return args

def construct_plot_tables(
    df: pl.DataFrame,
    daily_dl: pl.DataFrame,
    n_days:int,
    tides_shapes: list,
    site_name:str ) -> go.Figure:
    
    temps_lowerbound = calc_limit("min", daily_dl, ["sea temperature", "min temp"], scale=1.0, round=True)
    temps_upperbound = calc_limit("max", daily_dl, ["sea temperature", "max temp"], scale=1.0, round=True)
    temps_shapes = get_temperature_stripes(n_days, "x2", temps_lowerbound, temps_upperbound)

    z_matrix = df.pivot(
        on="hour", index="day", values="status_val", aggregate_function="first"
    )
    text_matrix = df.pivot(
        on="hour", index="day", values="weather_icon", aggregate_function="first"
    )

    days = z_matrix["day"].to_list()
    hours = [col for col in z_matrix.columns if col != "day"]

    z_data = z_matrix.select(hours).to_numpy()
    text_data = text_matrix.select(hours).to_numpy()

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
        text=text_data,
        texttemplate="%{text}",
        textfont={"size": 16, "color": "black"},
        hoverinfo="text",
        name=site_name +" Outlook",
        hovertext=[[f"Day: {d}<br>Hour: {h}:00" for h in hours] for d in days],
    )

    tab_multiplier = 0.80
    tabs = make_subplots( # Construct result, which is two side by side plots.
        rows=1,
        cols=2,
        column_widths=[tab_multiplier, 1 - tab_multiplier],
        shared_yaxes=True,
    )
    tabs.add_annotation( # handle subtitle manually for control over position
        text="Categories",
        x=0.5,
        y=1.12,
        xref="x domain",
        yref="paper",
        showarrow=False,
        xanchor="center",
    )
    tabs.add_annotation( # handle subtitle manually for control over position
        text="Temperatures",
        x=0.5,
        y=1.12,
        xref="x2 domain",
        yref="paper",
        showarrow=False,
        xanchor="center",
    )
    tabs.add_trace(table_heatmap, row=1, col=1)

    for key,value in constraints.items():
        symbol=value.symbol
        tabs.add_trace( # add dummy trace for each entry to show up in legend
            go.Scatter(x=[None],y=[None],mode="markers",marker={"size": 0},name=symbol+" "+key,legend="legend2",hoverinfo="skip"),
            row=1,
            col=1,
        )

    tabs.add_trace(
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

    tabs.add_trace(
        go.Scatter(
            x=daily_dl["mean temperature"],
            y=daily_dl["day"],
            mode="markers",
            marker={"color": "#ffffff", "size": 7, "line": {"color": "#0f172a", "width": 1.5}},
            name="Avg",
            hovertemplate="Date: %{y}<br>Mean: %{x:.1f}°C<extra></extra>",
        ),
        row=1,
        col=2,
    )

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


def construct_plot_daily( df: pl.DataFrame ) -> go.Figure:
    unique_days = df["day"].unique(maintain_order=True).to_list()
    global_tide_min = calc_limit("min", df, "sea_level_height_msl")
    global_tide_max = calc_limit("max", df, "sea_level_height_msl")
    global_wind_limit = calc_limit("max", df, "wind_speed_10m")
    global_wave_limit = calc_limit(
        "max", df, ["calc_wave_height", "swell_wave_height", "wind_wave_height"]
    )

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.20, 0.35, 0.15, 0.30],
    )

    for i, day in enumerate(unique_days):
        day_d = df.filter(pl.col("day") == day)
        for m, val in measures.items():
            if val["type"] == "data":
                continue
            vis = val["visible_start"] and i == 0
            if val["type"] == "scatter":
                fig.add_trace(
                    go.Scatter(
                        x=day_d["time"],
                        y=day_d[m],
                        name=val["name"],
                        legendgroup=val["name"],
                        visible=vis,
                    ),
                    row=val["row"],
                    col=1,
                )
            elif val["type"] == "arrow_dir":
                arrow_plot(fig, day_d, m, val["arg"], row=val["row"], vis=vis)

    fig.update_layout(
        dragmode=False,
        margin={"t": 20, "b": 10},
        yaxis={"range": [global_tide_min, global_tide_max], "ticksuffix": " m"},
        yaxis2={"range": [0, global_wind_limit], "ticksuffix": " km/h"},
        yaxis4={"range": [0, global_wave_limit], "ticksuffix": " m"},
        template="plotly_white",
        hovermode="x unified",
    )
    fig.update_yaxes(visible=False, row=3, col=1) 
    return fig


def render_html(grid:go.Figure, fig:go.Figure, date_start:str, n_days:int,site:Site):
    base_config = {
        "scrollZoom": False,
        "displaylogo": False,
        "displayModeBar": False,
        "doubleClickDelay": 1000,
        "responsive": True,
    }
    grid_html = grid.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        div_id="table-heatmap",
        config=base_config,
    )
    fig_html = fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id="my-sel",
        config=base_config,
    )

    dropdown_options_html = ""
    js_config_map = {}
    time_and_date_now = datetime.now(ZoneInfo(site.timezone)).strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )
    for i in range(n_days):
        full_day = datetime.fromisoformat(date_start).date() + timedelta(days=i)
        title = full_day.strftime("%A %d %B %y View")
        dropdown_options_html += f'<option value="view_{i}">{title}</option>\n'
        js_config_map[f"view_{i}"] = {
            "title": title,
            "day_label": full_day.strftime("%a %d"),
            "standard_mask": make_mask(i, n_days, False),
            "extended_mask": make_mask(i, n_days, True),
        }
    json_config_data = json.dumps(js_config_map)
    template = f"""
    <!DOCTYPE html>
    <html><head><style>
        body {{ font-family:sans-serif; background-color:white }}
        .mobile-dropdown-box {{
            margin: 4px 15px 0;
            font-family: sans-serif;
            display: flex;
            flex-direction: row;
            flex-wrap: wrap;
            align-items: center;
            justify-content: center;
            gap: 12px;
        }}
        select {{ padding: 12px; min-height: 48px; font-size: 16px; }}
        .extended-label {{
            min-height: 48px;
            padding: 0 8px;
            display: inline-flex;
            align-items: center;
            gap: 0 px;
            font-size: 14px;
            cursor: pointer;
        }}
        .extended-label input {{ width: 24px; height: 24px; }}
        .generated-at {{
            display: block;
            text-align: center;
            font-variant: small-caps;
        }}
    </style></head>
    <body>
        <h2>{site.name} Outlook</h2>
        <div>   {grid_html} </div>
        <div class="mobile-dropdown-box">
        <select id="mobile-navigator" onchange="triggerMobileUpdate(this.value)">
            {dropdown_options_html}
        </select>
        <label class="extended-label">
            <input id="extended-view" type="checkbox" onchange="triggerMobileUpdate()">
            Extended view
        </label>
        </div>
        <div>    {fig_html} </div><small class="generated-at">Generated at {time_and_date_now}</small>
        <script>
            const configData = {json_config_data};
            function triggerMobileUpdate() {{
                const selectedKey = document.getElementById("mobile-navigator").value;
                const graphDiv = document.getElementById("my-sel");
                const selection = configData[selectedKey];
    
                if (selection) {{
                    const extended = document.getElementById("extended-view").checked;
                    Plotly.update(
                        graphDiv,
                        {{visible: extended ? selection.extended_mask : selection.standard_mask}},
                        {{title: extended ? selection.title + " — Extended" : selection.title}}
                    );
                }}
            }}
            document.getElementById("table-heatmap").on("plotly_click", (eventData) => {{
                const point = eventData.points[0];
                if (point.data.type !== "heatmap") {{
                    return;
                }}

                const selectedKey = Object.keys(configData).find(
                    key => configData[key].day_label === point.y
                );
                if (selectedKey) {{
                    document.getElementById("mobile-navigator").value = selectedKey;
                    triggerMobileUpdate();
                }}
            }});
            triggerMobileUpdate();
        </script>
    </body>
    </html>
    """
    return template

def build_wave_expr(angle_l,angle_h): 
       return  (pl.when(pl.col("swell_wave_direction").is_between(angle_l, angle_h))
        .then(pl.col("swell_wave_height") ** 2)
        .otherwise(0)
        + pl.when(pl.col("secondary_swell_wave_direction").is_between(angle_l, angle_h))
        .then(pl.col("secondary_swell_wave_height") ** 2)
        .otherwise(0)
        + pl.when(pl.col("wind_wave_direction").is_between(angle_l, angle_h))
        .then(pl.col("wind_wave_height") ** 2)
        .otherwise(pl.col("lower_wind_bound"))
    ).sqrt()

def build_constraints_exprs(site,constraints):
    #Build polars expressions for bounds and config specified in 'site' for traffic light colour and symbol.
    expr=pl 
    for x,val in site.red.above.items():
        expr = expr.when(pl.col(constraints[x].column) > val).then(0)
    for x,val in site.red.below.items():
        expr = expr.when(pl.col(constraints[x].column) <= val).then(0)
    for x,val in site.amber.above.items():
        expr = expr.when(pl.col(constraints[x].column) > val).then(1)
    for x,val in site.amber.below.items():
        expr = expr.when(pl.col(constraints[x].column) <= val).then(1)
    i_expr=pl;
    for x,val in site.icon.above.items():
        i_expr = i_expr.when(pl.col(constraints[x].column) > val).then(pl.lit(constraints[x].symbol))
    for x,val in site.icon.below.items():
        i_expr = i_expr.when(pl.col(constraints[x].column) <= val).then(pl.lit(constraints[x].symbol))
   
    return expr.otherwise(2), i_expr.otherwise(pl.lit(""))    # pyright: ignore[reportAttributeAccessIssue]

def process_dataframe(df,site):
    # Define the forecast wave height as Root Sum of Squares of waves, 
    # for each swell or wind wave in the allowed direction. If wind wave isn't in that direction,
    # the sum should use the calculated wind wave in a sheltered area based on fetch provided.
    # Then add traffic-light categories based on acceptable conditions
    # and condition icons - emojis from symbol['Wind'] etc.
    # finally create a new 'daily' dataframe with per-day max,min,mean measures.

    # factor uses Carter formula assuming units in km and km/h .
    wind_factor=0.004528*math.sqrt(site.sheltered_distance)
    rss = build_wave_expr(site.sheltered_angles[0], site.sheltered_angles[1])

    # Loop over all constraints provided in 'site' to form conditional expressions.
    traffic_expr, icon_expr = build_constraints_exprs(site,constraints)

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
    daily = (
        df.group_by(pl.col("time").dt.date(), pl.col("day"))
        .agg(
            pl.col("temperature_2m").max().alias("max temp"),
            pl.col("temperature_2m").min().alias("min temp"),
            pl.col("sea_surface_temperature").mean().alias("sea temperature"),
            pl.col("temperature_2m").mean().alias("mean temperature"),
        )
        .sort("time"))
    return df, daily

def main(argv: list[str] | None = None) -> None:
    args = parse_cli_args(argv)

    try: 
        pydant = TypeAdapter(dict[str, Site])
        with open(args.config, "r") as f:
            sites= pydant.validate_json(f.read())
    except FileNotFoundError:
        sys.exit(f"Error: The configuration file '{args.config}' could not be found.")
    site=sites.get(args.site)
    if not site:
        sys.exit(f"Error: The configuration file '{args.config}' does not contain an entry '{args.site}'.")
   
    date_start_str = args.date_start.isoformat() 

    sunrise, sunset = local_sun_times(site.location, site.timezone, args.date_start, args.n_days)
    start_hour = max(EARLIEST_START_HOUR,int(min(sunrise)))
    end_hour = min(LATEST_END_HOUR,int(max(sunset)))

    forecast_measures = [ col for col, measure in measures.items() if measure["source"] == "forecast"]
    marine_measures = [ col for col, measure in measures.items() if measure["source"] == "marine"]
    
    date_end = (
        (args.date_start + timedelta(days=args.n_days - 1)).isoformat()
    )
    d_a = get_hourly(site.location, forecast_measures, date_start_str, date_end, "forecast")
    d_b = get_hourly(site.location, marine_measures, date_start_str, date_end, "marine")
    assert d_a is not None , "No forecast for {args.site}"
    assert d_b is not None , "No marine forecast for {args.site} location"
    
    # join maritime forecast  with standard weather, crop to useful hours
    df = (d_a.join(d_b, on="time", how="full", coalesce=True)
          .with_columns(pl.col("time").dt.convert_time_zone(site.timezone))
          .filter(pl.col("time").dt.hour().is_between(start_hour, end_hour)))  
    
    df,daily=process_dataframe(df,site) # do all weather-related processing

     # Construct figures in Plotly 
    tides_shapes = block_out_night(sunrise, sunset, start_hour, end_hour, args.n_days)

    two_tables = construct_plot_tables(df, daily, args.n_days, tides_shapes,site.name)
    fig = construct_plot_daily(df)

    #turn plotly figures into html+js
    output=render_html(two_tables,fig,date_start_str,args.n_days,site)
    sys.stdout.write(output)


if __name__ == "__main__":
    main()
