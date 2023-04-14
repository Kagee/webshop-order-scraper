# homelab-organizer

1. ~Web app for organizing stuff in your homelab.~ (not yet, have to finish 2. first)
2. Command line scraper for orders and item info from webshop(s)

## Requirements

Python 3.9 or later. Should support both Linux and Windows.

Requires Firefox installed, not from snap (see instructions).

## Logging / output

You can control logging by overriding `LOGGING` by creating a `hlo/settings/logging.py`

Look in `hlo/settings/django.py` for an example `LOGGING` [dictConfig](https://docs.python.org/3/library/logging.config.html)

Be aware that the Django command --verbosity argument will override the loglevel you set.

## Scraping of webshops

Requires Firfox. Chrome is to difficult to print to PDF from. Firefox installed as a snap on Ubuntu is not supported. To change to a apt install on i.e. Ubuntu 22.04, read [this](https://www.omgubuntu.co.uk/2022/04/how-to-install-firefox-deb-apt-ubuntu-22-04) article for omg!ubuntu.

### Aliexpress

Scrapes order list, item info and details to JSON, and saves a PDF copy of the Aliexpress item snapshot.

Try not to resize or move the autmomated browser window while scraping. You will be
prompted if you need to interract, i.e. accept a CAPTCHA. If you happen to watch and see that
a page is "stuck" and not loading, you can *try* a quick F5.

If you want to download some and some orders, you can start with i.e. `HLO_SCRAPER_ALI_ORDERS_MAX=10`,
and then increment with 10 for each run. Remember to use `--use-cached-orderlist` so you do not have
to scrape the order list every time.

````python
python manage.py scrape aliexpress --use-cached-orderlist
````

### Amazon

Currently can save order lists to HTML cache and convert to
JOSN that contains order is, total and date.

````python
# Scrape this year and archived orders orders on amazon.de
python manage.py scrape amazon --use-cached-orderlist

# Scrape orders from 2021 and 2023 on amazon.es
python manage.py scrape amazon --use-cached-orderlist --year 2021,2023 --not-archived --tld es

# Scrape all orders on amazon.co.jp from 2011 onwards, including archived orders
python manage.py scrape amazon --use-cached-orderlist --start-year 2022 --tld co.jp

# See help for details
python manage.py scrape --help
````

### Adafruit

1. Login to <https://www.adafruit.com/>
2. Click "Account" -> "My Account"
3. Click "Order History" (<https://www.adafruit.com/order_history>)
4. Click "Export Products CSV" and save "products_history.csv"
5. Click "Export Orders CSV" and save "order_history.csv"

Run the command too see where you should put the files.

````python
python manage.py scrape adafruit
````

## Linux 101

Terminal:

````python
cd /some/folder
git clone https://gitlab.com/Kagee/homelab-organizer.git
cd homelab-organizer
python3.9 -m venv ./venv # or newer
source ./venv/bin/activate
python -m pip install -U pip
cp example.env .env
nano .env # Edit .env to your liking
pip install -r requirements-dev.txt
# You probably want to do all this after a new git pull
python manage.py makemigrations
python manage.py migrate
````

## Windows 101

For PDF files in A4:

1. Printers and scanners
2. Microsoft print to PDF
3. Manage
4. Printer properties
5. Preferences
6. Advanced...
7. Paper Size: A4

CMD:

````bash
cd /some/folder
git clone https://gitlab.com/Kagee/homelab-organizer.git # or Github Desktop/other
cd homelab-organizer
python3.9 -m venv ./venv # or newer
venv\Scripts\activate
python -m pip install -U pip
cp example.env .env
notepad .env # Edit .env to your liking
# You probably want to do all this after a new git pull
pip install -r requirements-dev.txt
python manage.py makemigrations
python manage.py migrate
````

## Acknowledgements

For steadfast bug fixing, having orders that totally scramble my scraping, and coming up with those excellent ideas when I have been struggling with a bug for an hour.

[![neslekkim](https://github.com/neslekkim.png/?size=50)  
neslekkim](https://github.com/neslekkim)

## Why

* Am i not using `webdriver.print_page` to get a PDF?
  * In testing it created redonkulously large PDFs. We are talkin 40-60 MB when printing via Mozilla/Microsoft printers created sub 10MB PDFs

## Notes and ideas

* <https://rk.edu.pl/en/fulltext-search-sqlite-and-django-app/>
