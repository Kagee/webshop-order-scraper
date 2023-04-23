# webshop-scraper

Command line scraper for orders and item info from webshop(s)

This project was separated from it's parent project [Homelab Organizer](https://gitlab.com/Kagee/homelab-organizer) (having outgrown it), a web-based tool (Django) for keeping control of items and tools in your homelab.

## Status
* [Adafruit](#adafruit)
  * Complete. Does not require login. Requires minimal manual work (download) before starting.
* [Aliexpress](#aliexpress)
  * Almost complete. Missing standarised JSON+zip output. Login, parse order lists, save cache item info finished.
* [Amazon](#amazon)
  * Mostly complete. Login, parse order lists, cache item info.
* [Distrelec](#distrelec)
  * Initial. Login.
* [eBay](#ebay)
  * Started. Login, get all order numbers, get base info for orders. 
* [IMAP](#imap)
  * Complete. Currently only used to extract old eBay order numbers from email.
* [Pimoroni](#pimoroni)
  * Initial. Loging, list and cache order lists.

## Requirements

Python 3.9 or later. Should support both Linux and Windows.  
Requires Firefox installed, not from snap (see instructions).


## Scraping of webshops

Requires Firfox. Chrome is to difficult to print to PDF from.  
Firefox installed as a snap on Ubuntu is not supported.  
To change to a apt install on i.e. Ubuntu 22.04, read [this](https://www.omgubuntu.co.uk/2022/04/how-to-install-firefox-deb-apt-ubuntu-22-04) article for omg!ubuntu.

### Adafruit

1. Login to <https://www.adafruit.com/>
2. Click "Account" -> "My Account"
3. Click "Order History" (<https://www.adafruit.com/order_history>)
4. Click "Export Products CSV" and save "products_history.csv"
5. Click "Export Orders CSV" and save "order_history.csv"

Run the command too see where you should put the files.

````python
python scrape.py adafruit
````

### Aliexpress

Scrapes order list, item info and details to JSON, and saves a PDF copy of the Aliexpress item snapshot.

Try not to resize or move the autmomated browser window while scraping. You will be
prompted if you need to interract, i.e. accept a CAPTCHA. If you happen to watch and see that
a page is "stuck" and not loading, you can *try* a quick F5.

If you want to download some and some orders, you can start with i.e. `WB_ALI_ORDERS_MAX=10`,
and then increment with 10 for each run. Remember to use `--use-cached-orderlist` so you do not have
to scrape the order list every time.

````python
python scrape.py aliexpress --use-cached-orderlist
````

### Amazon
Currently can save order lists to HTML cache and convert to
JOSN that contains order is, total and date.

````python
# Scrape this year and archived orders orders on amazon.de
python scrape.py amazon --use-cached-orderlist

# Scrape orders from 2021 and 2023 on amazon.es
python scrape.py amazon --use-cached-orderlist --year 2021,2023 --not-archived --tld es

# Scrape all orders on amazon.co.jp from 2011 onwards, including archived orders
python scrape.py amazon --use-cached-orderlist --start-year 2022 --tld co.jp

# See help for details
python scrape.py --help
````
### Distrelec

### eBay

### IMAP

### Pimoroni

## Installation (git)
### Linux, Mac OS X 101

Terminal:

````python
cd /some/folder
git clone https://gitlab.com/Kagee/webshop-scraper.git
cd webshop-scraper
python ./update.py
source ./venv/bin/activate
cp example.env .env
nano .env # Edit .env to your liking
````

### Windows 101

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
git clone https://gitlab.com/Kagee/webshop-scraper.git # or Github Desktop/other
cd webshop-scraper
python ./update.py
venv\Scripts\activate
cp example.env .env
notepad .env # Edit .env to your liking
````

## JSON Schema
{"format": "file-path"}
https://docs.pydantic.dev/usage/schema/#json-schema-types
https://gitlab.com/Kagee/webshop-scraper/-/raw/main/schema.json?inline=false

## Acknowledgements

For steadfast bug fixing, having orders that totally scramble my scraping, and coming up with those excellent ideas when I have been struggling with a bug for an hour.
<table>
<tr><td>

[![neslekkim](https://github.com/neslekkim.png/?size=50)  
neslekkim](https://github.com/neslekkim)
</td>
<td>

[![rkarlsba](https://github.com/rkarlsba.png/?size=50)  
rkarlsba](https://github.com/rkarlsba)
</td></tr>
</table>

## Why

* Am i using Firefox and not Chrome/Other?
  * Efficiently printg to PDF is much easier in Firefox. Chorome does also not appear to give actual text in PDFs after printing as Firefox does.

* Am i not using `webdriver.print_page` to get a PDF?
  * In testing it created redonkulously large PDFs. We are talkin 40-60 MB when printing via Mozilla/Microsoft printers created sub 10MB PDFs
