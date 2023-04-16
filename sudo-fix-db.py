import os
import sys
from pathlib import Path
import subprocess


def remove(path):
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


sys.exit()

print(
    "This will nuke and reinitialize you database. Press enter to continue,"
    " Ctrl-Z to cancel."
)
input()
here = Path(os.getcwd())
if here.name != "homelab-organizer":
    print("I should be run from homelab-organizer")
    sys.exit()

print("Deleting databse ", "db-dev.sqlite3")
remove(here / "db-dev.sqlite3")

for migration in (here / Path("order_scraper/migrations/")).glob("0*.py"):
    print("Deleting migration ", migration)
    remove(migration)

print("Recreating migrations")
subprocess.run([sys.executable, "manage.py", "makemigrations"], check=False)

print("Migrating migrations (creating DB)")
subprocess.run([sys.executable, "manage.py", "migrate"], check=False)

print("Initializing shops")
subprocess.run(
    [sys.executable, "manage.py", "scrape", "--init-shops"], check=False
)
