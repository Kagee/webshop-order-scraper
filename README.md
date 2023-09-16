# webshop-scraper

Command line scraper for orders and item info from webshop(s)

This project was separated from it's parent project [Homelab Organizer](https://gitlab.com/Kagee/homelab-organizer) (having outgrown it), a web-based tool (Django) for keeping control of items and tools in your homelab.

## Output
Output from finished scrapers consists of one JSON and a ZIP in a subfolder of the `output/` folder.

The JSON file will follow the JSON schema defined in [output/schema.json](output/schema.json). Any extra data avaliable for the order or items will be added as keys to this file. All paths are relative to the root of the accompanying ZIP file. 


## Completed
* [Adafruit](#adafruit)
  * Complete. Does not require login. Requires minimal manual work (download) before starting.
* [Aliexpress](#aliexpress)
  * Complete. Requires creating a separate Firefox profile, configuring it, and logging in to Aliexpress in said profile.
* [Polyalkemi.no](#polyalkemino)
  * Complete.
* [IMAP](#imap)
  * Complete. Currently only used to extract old eBay order numbers from email.

## Missing export
* [Kjell.com](#kjellcom)
  * Scraping complete. Missing export

## Scraping not complete
* [Amazon](#amazon)
  * Mostly complete. Login, parse order lists, cache item info.
* [Distrelec](#distrelec)
  * Initial. Login.
* [eBay](#ebay)
  * Started. Login, get all order numbers, get base info for orders. 

* [Pimoroni](#pimoroni)
  * Initial. Loging, list and cache order lists.

## Requirements

Python 3.10 or later. Should support both Linux and Windows.  

Requires Firefox installed (not from snap, see instructions), and a profile setup for the scraping.

## Creating and configuring a separate Firefox profile

Run 
````bash
firefox -p
````

Create a new profile, named i.e. `selenum`. In the examples below you named the profile `selenium`, and your username is `awesomeuser``.

Find the path to the profile, you can start looking in these paths:
* Windows: `C:\Users\awesomeuser\AppData\Roaming\Mozilla\Firefox\Profiles\SOMETHINGRANDOM.selenium1`
* Linux / Mac: `/home/awesomeuser/.mozilla/firefox/SOMETHINGRANDOM.selenium1`

Add this path to the `WS_FF_PROFILE_PATH_WINDOWS/LINUX/DARWIN` config variable in .env.

## Installing Firefox outside of Snap on Ubuntu

Firefox installed as a snap on Ubuntu is not supported.  
To change to a apt install on i.e. Ubuntu 22.04, read [this](https://www.omgubuntu.co.uk/2022/04/how-to-install-firefox-deb-apt-ubuntu-22-04) article for omg!ubuntu.

## Scrapers

### Adafruit

1. Login to <https://www.adafruit.com/>
2. Click "Account" -> "My Account"
3. Click "Order History" (<https://www.adafruit.com/order_history>)
4. Click "Export Products CSV" and save "products_history.csv"
5. Click "Export Orders CSV" and save "order_history.csv"

Run the command too see where you should put the files.

````python
python scrape.py --loglevel DEBUG adafruit
````
````python
python scrape.py --loglevel DEBUG adafruit --to-std-json
````

### Aliexpress

Scrapes order list, item info and details to JSON, and saves a PDF copy of the Aliexpress item snapshot.

Aliexpress has a really annoying CAPTCHA that failes even if you do it manually, as long as the browser is automated.

To bypass this, open your `selenium` firefox profile, and log in to Aliexpress manually before each scraping session.

Try not to resize or move the autmomated browser window while scraping. You will be
prompted if you need to interract, i.e. accept a CAPTCHA. If you happen to watch and see that
a page is "stuck" and not loading, you can *try* a quick F5.

If you want to download some and some orders, you can start with i.e. `WB_ALI_ORDERS_MAX=10`,
and then increment with 10 for each run. Remember to use `--use-cached-orderlist` so you do not have
to scrape the order list every time.

````python
python scrape.py --loglevel DEBUG aliexpress --use-cached-orderlist
````

````python
python scrape.py --loglevel DEBUG aliexpress --to-std-json
````

### Polyalkemi.no
This scraper supports the arguments 
* `--skip-item-thumb`
* `--skip-item-pdf`
* `--skip-order-pdf`

They will skip storing the item thumbnail, item PDF print, and order invoice for this scraper.

````python
python scraper.py --loglevel DEBUG polyalkemi 
````

````python
python scraper.py --loglevel DEBUG polyalkemi --to-std-json 
````

### Kjell.com
````python
python scraper.py --loglevel DEBUG kjell
````
Export not yet supported.

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
git clone https://gitlab.com/Kagee/webshop-order-scraper.git
cd webshop-order-scraper
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
git clone https://gitlab.com/Kagee/webshop-order-scraper.git # or Github Desktop/other
cd webshop-order-scraper
python ./update.py
venv\Scripts\activate
cp example.env .env
notepad .env # Edit .env to your liking
````

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
