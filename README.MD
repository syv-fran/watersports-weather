This Python script gives a colour-coded matrix of good and bad times to go out kayaking/SUPping/sailing in the next week or so. Hours are marked by too much/little wind, waves, tide etc.

### FEATURES
- Interactive HTML - run the script to get an up-to-date forecast when you can, and then interact with the graphs offline when you are out on the water.
- Unlimited locations, adjustable limits of what conditions are RED, AMBER or GREEN for you.
- Uses marine forecast, but locations can be configured to be sheltered from some directions, giving more realistic wave heights for coasts and bays.
- Big buttons for wet gloved hands on phones.
- Visually represents daylight hours in your timezone(s).
- Temperature display based on UK Met Office colour categories for at-a-glance overview.
- Apply the same rules to all locations, or set up your SUP spot to prefer less wind than your sailing trip.
- Inland lakes? Define them as sheltered from all directions and set max distance from land to calculate waves.

### QUICKSTART
Once you have downloaded the repository and ensured Python is installed:

    cd watersports-weather
    pip install -r requirements.txt
    python weather.py -o forecast.html
View `forecast.html` in your browser.
By default it reads locations (specified as latitude and longitude) and rules from 
`weather.json`. Customise this after examining the examples and re-run `weather.py`.

### COMMAND LINE USAGE

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

### REGULAR USAGE

Can be integrated with a personal webserver, dashboard system or auto-scheduled emails for seafarers with intermittent connections. If using emails, send as an attachment to ensure Javascript works correctly.

### CAUTION

No warranty. You are responsible for your decisions based on this forecast, which may be wrong.
Good maritime practice requires gathering information from multiple sources and assessing its credibility.
