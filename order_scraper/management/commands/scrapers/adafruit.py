# pylint: disable=unused-import
import os
import re
import time
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from lxml.etree import tostring
from lxml.html.soupparser import fromstring
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from .base import BaseScraper, PagePart


# Scraper for trying out code for other scrapers
class AdafruitScraper(BaseScraper):
    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options, __name__)
        self.setup_cache("adafruit")
        self.setup_templates()

    def part_to_filename(self, part: PagePart, **kwargs):
        return None

    def usage(self):
        print(f"""

    USAGE:
    ==================================================
    Login to https://www.adafruit.com/
    Click "Account" -> "My Account" 
    Click "Order History" (https://www.adafruit.com/order_history)
    Click "Export Products CSV" and save "products_history.csv" to 
        {self.cache['BASE']}
    Click "Export Orders CSV" and save "order_history.csv" to 
        {self.cache['BASE']}
        """)

    def parse_order_csv(self):
        with open(self.ORDERS_CSV, newline="", encoding="utf-8") as csvfile:
            orders_dict = list(csv.DictReader(
                csvfile, dialect=csv.excel
            ))
            orders = {}
            for order in orders_dict:
                order['date_purchased'] = datetime.strptime(
                    order['date_purchased'], "%Y %m %d %H:%M:%S"
                )
                orders[order['order_id'].split(" ")[0]] = order
            return orders


    def combine_orders_items(self, orders):
        with open(self.ITEMS_CSV, newline="", encoding="utf-8") as csvfile:
            items = list(csv.DictReader(
                csvfile, dialect=csv.excel
            ))
        for item in items:
            order_id = item["order"]
            del item["order"]
            if 'items' not in orders[order_id]:
                orders[order_id]["items"] = {}
            item_id = item["product id"]
            del item["product id"]
            orders[order_id]["items"][item_id] = item
        return orders


    def command_scrape(self):
        if not self.can_read(self.ORDERS_CSV):
            self.usage()
            raise CommandError("Could not find order_history.csv")
        if not self.can_read(self.ITEMS_CSV):
            self.usage()
            raise CommandError("Could not find products_history.csv")

        orders = self.combine_orders_items(self.parse_order_csv())
        self.pprint(orders)

    def browser_login(self, _):
        return False

    def setup_templates(self):
        self.ORDERS_CSV = self.cache["BASE"] / "order_history.csv"
        self.ITEMS_CSV = self.cache["BASE"] / "products_history.csv"
