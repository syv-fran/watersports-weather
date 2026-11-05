### Configuration

The config file (defaulting to `weather.json`) should be a list of sites, enclosed by curly braces in standard JSON format. The repository contains two examples, `weather.json` and `example-single.json`.

#### Basics

Each site should have a label, name and location specified as \[latitude,longitude\]. For example:
 
    "kayaking1": {
            "name": "South Bay Kayaking",
            "location": [
                36.2,
                -6.0
            ],
    }
The label ``kayaking1`` can be used on the command line to select a single site (the default is to display all sites with locations), and should be unique.

Rules should be listed for each site by severity colour (red or amber) followed by whether it is triggered above (>=) or below (<) the value in the given [units](#Units). 
For example, add this after the location for a beginner stand up paddler who doesn't like the rain, or wading through mud at low tide:

        "red": {
            "above": {
                "Wind": 12.0,
                "Waves": 0.2
             }
            }
        "amber": {
            "above": {
                "Rain": 0.0
            },
            "below": {
                Tide: - 0.4
            }
        }

An hour will be coloured green if it does not match a red or amber rule.

#### Icons

The "icon" configuration sets rules for emojis to appear in each hour when above/below the constraints. This way, you can see why
an hour is coloured red or amber. Or maybe you want to know about the waves, but they aren't a bad thing!

There is only room for two emojis at once on the graph. More will be marked with a "+" and can be examined via a tooltip.

#### Constraints

Current constraints are Wind, Wave, Rain and Tide. 


#### Sheltered bays and wave heights

A marine forecast returns the estimated wave heights at sea, without interactions from nearby coastal features. However, if we are on the south coast, and the wind is blowing from the north, there will be no ocean swell, just wind waves that are whipped up in the short distance from land. 
For a south coast location at most 300m from shore, include:

    "sheltered_distance": 0.3,
            "sheltered_angles": [
                270.0,
                90.0
            ],
You may need some trial and error to get the best configuration for your sheltered bay, because complicated features like  waves diffracting around headlands, land height, and surf characteristics are not modelled.

By using the "Extended View" checkbox you can examine separate components of the wave forecast to see how they coincide with actual conditions. Calculations use Carter formula + root
sum of squares.

For inland locations, set ``sheltered_angles": [360,0]`` . Sea temperature and swell heights will usually be unavailable.

#### Units {#units}

- Waves: m 
- Rain: mm 
- Wind: km/h
- Tide: m  
- Temperature: Celsius

Future work: Accommodate preferred units?

#### Global Defaults

A configuration file entry called `global`, if present, helps to make the config file more concise for multiple sites. Its contents are defaults, overridden by constraints elsewhere.

    "global": {
        "red": {
            "above": {
                "Waves": 1
             }
        }
    }

#### Time and date considerations

- In most situations, you do not need to specify the timezone, but you may do so:
 `` "timezone": "Europe/Madrid", ...``

- Hours displayed are 8am-8pm, greyed out between sunset and sunrise.

- Forecasting more than two weeks ahead is not supported. Historical data may be limited. Data is sourced by combining regular and marine forecasts from OpenMETEO.com .
