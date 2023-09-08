# pylint: disable=unused-import
import base64
import os
import re
import time
import decimal
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Union
from urllib.parse import urlparse, urlencode, parse_qs
import requests
import filetype
import json

from lxml.etree import tostring
from lxml.html import HtmlElement
from lxml.html.soupparser import fromstring
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from . import settings
from .base import BaseScraper

# pylint: disable=unused-import
from .utils import AMBER, BLUE, GREEN, RED


class PolyalkemiScraper(BaseScraper):
    tla: Final[str] = "PAI"
    name: Final[str] = "Polyalkemi.no"
    simple_name: Final[str] = "polyalkemi.no"

    # Methods that use Selenium to scrape webpages in a browser

    def browser_save_item_and_attachments(self):
        pass

    def browser_save_item_thumbnail(self):
        pass

    def browser_cleanup_item_page(self) -> None:
        pass

    def browser_expand_item_page(self):
        pass

    def browser_load_order_list(self):
        pass

    # Random utility functions

    def setup_templates(self):
        # pylint: disable=invalid-name
        # URL Templates
        self.ORDER_LIST_URL: str = "https://polyalkemi.no/min-konto/orders/"
        self.ORDER_URL: str = (
            "https://polyalkemi.no/min-konto/view-order/{order_id}/"
        )
        # pylint: disable=invalid-name
        # self.THUMB_FILENAME_TEMPLATE = str(
        #    self.cache["ORDERS"] / "{order_id}/item-thumb-{item_id}.png"
        # )
        self.ORDER_LIST_JSON_FILENAME = (
            self.cache["ORDER_LISTS"] / f"{self.simple_name}-orders.json"
        )

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        pass

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your Polyalkemi.no orders.
        """
        try:
            orders = self.browser_get_order_list_and_faktura()
            self.pprint(orders)
            for order in orders:
                self.browser_get_order_details()
                pass

            # cleanup:
            # cssselect:
            # .elementor-location-header
            # xpatg
            # //h2[contains(text(), 'Tilsvarende produkter')]/ancestor::section
            # //footer/parent::div

            # input()
        except NoSuchWindowException:
            pass
        self.browser_safe_quit()

    def browser_get_order_details(self, order):
        order_id = order["id"]
        order_dir = Path(self.cache["ORDERS"] / order_id)
        order_json = order_dir / "order.json"
        if self.can_read(order_json):
            return self.read(order_json,from_json=True)
        order_details = {}
        brws = self.browser_visit(self.ORDER_URL.format(order_id = order_id))
        input()
        
        #self.write(order_details, to_json=True)
    
    def browser_visit(self, url):
        brws = self.browser_visit_page(
            url, default_login_detect=False
        )
        try:
            brws.find_element(
                By.CSS_SELECTOR, "form.login"
            )  # No ned to put in variable
            self.log.error(
                RED("You need to login manually. Press enter when completed.")
            )
            input()
            brws = self.browser_visit_page(
                url, default_login_detect=False
            )
        except NoSuchElementException:
            pass

    def browser_get_order_list_and_faktura(self):
        if self.options.use_cached_orderlist:
            if self.can_read(self.ORDER_LIST_JSON_FILENAME):
                return self.read(self.ORDER_LIST_JSON_FILENAME, from_json=True)
        self.log.info("Could not find cached orderlist.")
        brws = self.browser_visit(self.ORDER_LIST_URL)
      
        orders_table = brws.find_element(
            By.CSS_SELECTOR, "table.woocommerce-orders-table"
        )
        order_rows = orders_table.find_elements(By.CSS_SELECTOR, "tbody tr")
        orders = []
        for order_row in order_rows:
            order_cols = order_row.find_elements(By.CSS_SELECTOR, "td")
            order_id = order_cols[0].text[1:]

            order_dir = Path(self.cache["ORDERS"] / order_id)
            self.makedir(order_dir)
            order_pdf_path = order_dir / "faktura.pdf"
            if not self.can_read(order_pdf_path):
                # TODO: Download PDF
                order_faktura = order_cols[4].find_element(
                    By.XPATH, "//a[contains(text(),'Faktura')]"
                )

                for pdf in self.cache["TEMP"].glob("*.pdf"):
                    # Remove old/random PDFs
                    os.remove(pdf)
                self.log.debug(
                    "Opening PDF, waiting for it to download in background"
                )
                order_faktura.click()
                time.sleep(2)
                pdf = list(self.cache["TEMP"].glob("*.pdf"))
                while not pdf:
                    pdf = list(self.cache["TEMP"].glob("*.pdf"))
                    time.sleep(3)
                self.wait_for_stable_file(pdf[0])
                self.move_file(pdf[0], order_pdf_path)

            order_date = datetime.strptime(order_cols[1].text, "%d/%m/%Y")
            order_status = order_cols[2].text

            total_re = r"(-?)kr (\d*.*\.\d*) for (-?)(\d*) produkt(?:er|)"
            m = re.match(total_re, order_cols[3].text)
            order_total = decimal.Decimal(f"{m[1]}{m[2]}")
            item_count = int(f"{m[3]}{m[4]}")
            self.log.debug(
                "ordre/dato/status/total/items: %s/%s/%s/%s/%s",
                order_id,
                order_date,
                order_status,
                order_total,
                item_count,
            )
            orders.append(
                {
                    "id": order_id,
                    "date": order_date,
                    "status": order_status,
                    "total": str(order_total),
                    "item_count": item_count,
                }
            )
        self.write(self.ORDER_LIST_JSON_FILENAME, orders, to_json=True)
        return orders

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with schema,
         and a .zip with all attachements
        """

        structure = self.get_structure(
            self.name,
            None,
            "https://polyalkemi.no/min-konto/view-order/{order_id}/",
            "https://polyalkemi.no/produkt/{item_id}/",
        )

        # structure["orders"] = orders
        # self.pprint(orders)
        self.output_schema_json(structure)

    # Class init
    def __init__(self, options: Dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        self.simple_name = "polyalkemi.no"
        super().setup_cache(Path("polyalkemi-no"))
        self.setup_templates()
