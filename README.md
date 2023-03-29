# homelab-organizer
Web app for organizing stuff in your homelab.

## Scraping of webshops
This requires Firefox. Firefox installed as a snap on Ubuntu is not supported. To change to a apt install on i.e. Ubuntu 22.04, read [this](https://www.omgubuntu.co.uk/2022/04/how-to-install-firefox-deb-apt-ubuntu-22-04) article for omg!ubuntu.
### Aliexpress
Scrapes order list, item info and details, and saves a PDF copy of the Aliexpress item snapshot.

````
source ./venv/bin/activate
pip install -r requirements.txt
cp dev.env .env
# Edit .env to your liking
python manage.py scrape aliexpress --cache
````

### Amazon.de
Planned, not implemented.

## Windows 101
CMD:
````
cd /some/folder
git clone https://github.com/Kagee/homelab-organizer.git # or Github Desktop
cd homelab-organizer
python3.10 -m venv ./venv
venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements-dev.txt
cp dev.env .env
notepad .env # Edit .env to your liking
python manage.py migrate
python manage.py scrape aliexpress --cache
````