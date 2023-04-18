#!/usr/bin/env python3

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from sqlite3 import OperationalError


def remove(path):
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


nuke = input("This will nuke and reinitialize you database. Superusers will be preserved. Continue? (y/N): ")
if nuke.lower() != "y":
    print("Non-positive answer, bailig....!")
    sys.exit()

here = Path(os.getcwd())
if here.name != "homelab-organizer":
    print("I should be run from homelab-organizer")
    sys.exit()

print("Saving superusers")
conn = sqlite3.connect("db-dev.sqlite3")
cu = conn.cursor()
sql_commands = []
sql_commands.append("PRAGMA foreign_keys=OFF;")
sql_commands.append("BEGIN TRANSACTION;")
conn.row_factory = sqlite3.Row
try:
    for line in conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = 'auth_user';"
    ).fetchall():
        if line["sql"]:
            sql_commands.append(
                line["sql"].replace(
                    'CREATE TABLE "', 'CREATE TABLE IF NOT EXISTS "'
                )
            )
    for line in conn.execute(
        "SELECT * FROM 'auth_user' WHERE is_superuser = 1;"
    ).fetchall():
        sql_commands.append(
            "INSERT INTO auth_user"
            f" VALUES({line['id']},'{line['password']}',NULL,"
            f"{line['is_superuser']},'{line['username']}','',"
            f"'{line['email']}',{line['is_staff']},"
            f"{line['is_active']},'{line['date_joined']}','');"
        )
except OperationalError:
    pass

sql_commands.append("COMMIT;")
conn.close()

print("Deleting databse ", "db-dev.sqlite3")
while True:
    try:
        remove(here / "db-dev.sqlite3")
        break
    except PermissionError as pe:
        input(f"Failed to delete DB, please fix and press enter: {pe}")

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

print("Restoring superusers")
conn = sqlite3.connect("db-dev.sqlite3")
cu = conn.cursor()
for sql in sql_commands:
    conn.execute(sql)
conn.close()

nuke = input("Load AliExpress to DB? (y/N): ")
if nuke.lower() == "y":
    subprocess.run(
        [
            sys.executable,
            "manage.py",
            "scrape",
            "aliexpress",
            "--load-to-db",
            "--db-shop-id",
            "3",
        ],
        check=False,
    )

nuke = input("Load Adafruit to DB? (y/N): ")
if nuke.lower() == "y":
    subprocess.run(
        [
            sys.executable,
            "manage.py",
            "scrape",
            "adafruit",
            "--load-to-db",
            "--db-shop-id",
            "1",
        ],
        check=False,
    )
