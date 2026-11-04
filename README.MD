<html> <img width="100" height="132/" alt="Screenshot" align="left" src="https://github.com/user-attachments/assets/54a4f9c1-e7f4-491e-8baa-6fe10f240887" />This Python script gives a colour-coded matrix of good and bad times next week to go out kayaking, stand up paddleboarding or sailing. Hours are colour-coded for too much or too little wind, waves, tide and rain. </html>

## [Live Demo Here](https://syv-fran.github.io/watersports-weather/): current weather, fixed locations and rules.
### Features
- Interactive, responsive HTML. Run the script to get an up-to-date forecast when you can, and then interact with the graphs offline when you are out on the water.
- Unlimited locations, with adjustable limits of what conditions are RED, AMBER or GREEN for you.
- Uses marine forecast, but locations can be configured to be sheltered from some directions, giving more realistic wave heights for coasts and bays.
- Big buttons for wet gloved hands on phones.
- Visually represents daylight hours in your timezone(s).
- Temperature display at a glance based on UK Met Office colour categories.
- Apply the same rules to all locations, or let your SUP spots prefer less wind than your sailing venues.
- Inland lakes? Define them as sheltered from all directions and set max distance from land to calculate waves.

### Quickstart
Once you have downloaded the repository and ensured Python is installed:

    cd watersports-weather
    pip install -r requirements.txt
    python weather.py -o forecast.html
View `forecast.html` in your browser.
By default it reads locations (specified as latitude and longitude) and rules from 
`weather.json`. Customise this after examining the examples and re-run `weather.py`.

### Usage Suggestions

Can be integrated with a personal webserver, dashboard system or auto-scheduled emails for seafarers with intermittent connections. If using emails, send as an attachment to ensure Javascript works correctly.

### Caution

No warranty. You are responsible for your decisions based on this forecast, which may be wrong.
Good maritime practice requires gathering information from multiple sources and assessing its credibility.

### Command Line Details

    usage: weather.py [-h] [--config CONFIG] [--site SITE] [-o OUTPUT] [n_days] [date_start]

    Generate html weather for today or specified date

    positional arguments:
    n_days               number of forecast days
    date_start           start date as YYYY-MM-DD

    options:
    -h, --help           show this help message and exit
    --config CONFIG      Use this JSON config file
    --site SITE          Use this location from config file
    -o, --output OUTPUT  Write generated HTML to this file instead of standard output
