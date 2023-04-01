# homelab-organizer
1. Web app for organizing stuff in your homelab.
2. Command line scraper for orders and item info from webshop(s)

## Requirements
Python 3.9 or later

## Logging / output
You can control logging by creating `hlo/settings/logging.py`

Look in `hlo/settings/django.py` for example

## Scraping of webshops
This requires Firefox. Firefox installed as a snap on Ubuntu is not supported. To change to a apt install on i.e. Ubuntu 22.04, read [this](https://www.omgubuntu.co.uk/2022/04/how-to-install-firefox-deb-apt-ubuntu-22-04) article for omg!ubuntu.

### Aliexpress
Scrapes order list, item info and details, and saves a PDF copy of the Aliexpress item snapshot.

Try not to resize or move the autmomated browser window while scraping. You will be
prompted if you need to interract, i.e. accept a CAPTCHA. If you happen to watch and see that
a page is "stuck" and not loading, you can *try* a quick F5.

If you want to download some and some orders, you can start with i.e. `HLO_SCRAPER_ALI_ORDERS_MAX=10`, 
and then increment with 10 for each run. Remember to use `--cache-orderlist` so you do not have
to scrape the order list every time.

````
python manage.py scrape aliexpress
````

### Amazon.de
Planned, not implemented.

````
python manage.py scrape amazon.de
````

## Linux 101
Terminal:
````
cd /some/folder
git clone https://github.com/Kagee/homelab-organizer.git
cd homelab-organizer
python3.9 -m venv ./venv
source ./venv/bin/activate
python -m pip install -U pip
pip install -r requirements-dev.txt
cp dev.env .env
nano .env # Edit .env to your liking
python manage.py migrate
````

## Windows 101
CMD:
````
cd /some/folder
git clone https://github.com/Kagee/homelab-organizer.git # or Github Desktop
cd homelab-organizer
python3.9 -m venv ./venv
venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements-dev.txt
cp dev.env .env
notepad .env # Edit .env to your liking
python manage.py migrate
````