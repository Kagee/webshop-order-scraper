# pylint: disable=unused-import
import base64
from curses import is_term_resized
import os
import re
import time
import decimal
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Union
from urllib.parse import urlparse, urlencode, parse_qs

import requests
import filetype


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
            self.cache["ORDER_LISTS"] / "orders.json"
        )

    # Methods that use Selenium to scrape webpages in a browser
    def browser_cleanup_item_page(self):
        self.browser.execute_script("""
            function rx(xpath) {
                f = document.evaluate(
                    xpath, 
                    document.body, 
                    null, 
                    XPathResult.FIRST_ORDERED_NODE_TYPE
                    ).singleNodeValue
                if (f) {
                    f.remove();
                } else {
                    console.log("Failed to remove " + xpath)
                }
            }

            imgs=Array.from(document.querySelectorAll(".product-thumbnail-images img"));
            var img = document.createElement('img');
            img.src = imgs[0].src.replace('-100x100','');
            document.querySelector("h1").appendChild(img);
            imgs.forEach((el) => { 
                var img = document.createElement('img');
                img.src = el.src.replace('-100x100','');
                document.querySelector("body").appendChild(img);
            })

            rx("//a[contains(@href,'handlekonto')]//parent::div//parent::div");
            rx("//div[contains(@class, 'product-add-to-cart')]/parent::div/parent::div");
            rx("//h2[contains(text(), 'Tilsvarende produkter:')]//ancestor::section");
            rx("//div[@id='product-images']/parent::div/parent::div/parent::div/parent::div/parent::div/parent::div/parent::div")
            rx("//button[text()='Legg i handlekurv']/parent::div/parent::div")
            rx("//div[contains(@class, '_product_search')]/parent::div/parent::div")
            document.querySelector("footer").parentElement.remove();
            document.querySelector(".tabs").remove();
            document.querySelectorAll(".woocommerce-product-rating").forEach((el) => { el.remove(); })
            document.querySelector(".elementor-location-header").remove();

            document.querySelectorAll("*").forEach(
                (el) => { 
                    el.style.fontFamily = "unset";
                    el.className = ""; 
                    }
            ) 
            Array.from(document.getElementsByTagName('img')).forEach((el) => { 
                    if (el.height > 900) {
                    el.style.maxHeight = '900px'; 
                    }  
                } 
            );            
        """)

    def browser_get_order_details(self, order):
        order_id = order["id"]
        order_dir = Path(self.cache["ORDERS"] / order_id)
        self.makedir(order_dir)
        order_dir = Path(self.cache["ORDERS"] / order_id)
        order_json = order_dir / "order.json"
        if self.can_read(order_json):
            return self.read(order_json, from_json=True)

        order_details = {}
        order_url = self.ORDER_URL.format(order_id=order_id)
        self.log.debug("Visiting %s", order_url)
        brws = self.browser_get_instance()
        handle = brws.current_window_handle

        self.browser_visit(order_url)
        self.log.debug("Scraping order details")
        try:
            order_details["shipper"] = self.find_element(
                By.XPATH, '//span[@class="beklager"]//strong'
            ).text
        except AttributeError:
            pass
        try:
            order_details["trackingnumber"] = self.find_element(
                By.XPATH, '//span[@class="beklager"]//a'
            ).text
        except AttributeError:
            pass
        addresses = self.find_elements(By.XPATH, "//address")
        order_details["billing_address"] = addresses[0].text
        order_details["shipping_address"] = addresses[1].text

        order_detail_table = self.find_element(
            By.CSS_SELECTOR, "table.order_details"
        )
        item_rows = self.find_elements(
            By.CSS_SELECTOR, "tbody tr", order_detail_table
        )
        order_details["items"] = []
        for item_row in item_rows:
            tds = self.find_elements(By.CSS_SELECTOR, "td", item_row)
            a_element = self.find_element(By.CSS_SELECTOR, "a", tds[0])
            url = a_element.get_attribute("href")
            item_id_regexp = r".*polyalkemi\.no/produkt/([^/]*)/?"
            href_parts = re.match(item_id_regexp, url)
            item_id = href_parts.group(1)
            item_name = a_element.text
            item_count = int(
                self.find_element(
                    By.CSS_SELECTOR, "strong", tds[0]
                ).text.replace("\u00d7 ", "")
            )
            order_details["items"].append(
                {
                    "id": item_id,
                    "name": item_name,
                    "count": item_count,
                    "url": url,
                }
            )
        summary_rows = self.find_elements(
            By.CSS_SELECTOR, "tfoot tr", order_detail_table
        )
        for summary_row in summary_rows:
            what = self.find_element(
                By.CSS_SELECTOR, "th", summary_row
            ).text.lower()[:-1]
            about = self.find_element(By.CSS_SELECTOR, "td", summary_row)
            if what == "delsum":
                order_details["subtotal"] = about.text
            elif what == "frakt":
                span_amount = self.find_element(By.CSS_SELECTOR, "span", about)
                order_details["shipping"] = span_amount.text
            elif what == "totalt":
                span_amount = self.find_element(By.CSS_SELECTOR, "span", about)
                order_details["total"] = span_amount.text
                span_tax = self.find_element(
                    By.CSS_SELECTOR, "small span", about
                )
                order_details["tax"] = span_tax.text
            elif what == "betalingsmetode":
                # don't care
                pass
            else:
                self.log.error("Found unparsed row '%s'", what)
        for item in order_details["items"]:
            self.browser_save_item_page_pdf(order_dir, item)
        self.write(order_json, order_details, to_json=True)
        self.log.debug("Saved order #%s to json", order_id)
        self.browser.switch_to.window(handle)

    def browser_save_item_page_pdf(self, order_dir, item):
        brws = self.browser_get_instance()
        if not self.skip_order_pdf:
            item_pdf_file = (
                order_dir / Path(f"item-{ item['id'] }.pdf")
            ).resolve()
            if not self.can_read(item_pdf_file):
                self.log.debug("Making PDF for item %s", item["id"])
                brws.switch_to.new_window("tab")
                brws.get(item["url"])
                self.browser_cleanup_item_page()
                self.log.debug("Printing page to PDF")
                for pdf in self.cache["TEMP"].glob("*.pdf"):
                    os.remove(pdf)
                brws.execute_script("window.print();")
                self.wait_for_stable_file(self.cache["PDF_TEMP_FILENAME"])
                self.move_file(self.cache["PDF_TEMP_FILENAME"], item_pdf_file)
                self.log.debug("PDF moved to cache")
                brws.close()
                time.sleep(2)

    def browser_detect_handle_interrupt(self, expected_url):
        brws = self.browser_get_instance()
        try:
            self.log.debug("Looking for login form")
            brws.find_element(
                By.CSS_SELECTOR, "form.login"
            )  # No ned to put in variable
            self.log.error(
                RED("You need to login manually. Press enter when completed.")
            )
            input()
            brws.get(expected_url)
        except NoSuchElementException:
            self.log.debug("No login required")

    def browser_get_order_list_and_faktura(self):
        if self.options.use_cached_orderlist:
            if self.can_read(self.ORDER_LIST_JSON_FILENAME):
                self.log.info("Using cached orderlist.")
                return self.read(self.ORDER_LIST_JSON_FILENAME, from_json=True)
            else:
                self.log.info("Could not find cached orderlist.")
        else:
            self.log.info("Mot using cached orderlist.")

        self.browser_visit(self.ORDER_LIST_URL)
        brws = self.browser_get_instance()
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
            if not self.skip_order_pdf:
                order_pdf_path = order_dir / "faktura.pdf"
                if not self.can_read(order_pdf_path):
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
            total_parts = re.match(total_re, order_cols[3].text)
            order_total = decimal.Decimal(f"{total_parts[1]}{total_parts[2]}")
            item_count = int(f"{total_parts[3]}{total_parts[4]}")
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
        self.browser_visit(self.ORDER_LIST_URL)
        return orders

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your Polyalkemi.no orders.
        """
        try:
            orders = self.browser_get_order_list_and_faktura()
            # self.browser = self.browser_get_instance()
            # handle = self.browser.current_window_handle
            for order in orders:
                self.browser_get_order_details(order)
                # self.browser.switch_to.window(handle)
        except NoSuchWindowException as nswe:
            self.log.error("Closed browser because of %s", nswe)
        self.browser_safe_quit()

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
        self.skip_order_pdf = options.skip_order_pdf
        self.skip_item_pdf = options.skip_item_pdf
        super().setup_cache(Path("polyalkemi-no"))
        self.setup_templates()
