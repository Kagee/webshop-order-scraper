# pylint: disable=unused-import
import base64
import os
import re
import time
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

        # pylint: disable=invalid-name
        # self.THUMB_FILENAME_TEMPLATE = str(
        #    self.cache["ORDERS"] / "{order_id}/item-thumb-{item_id}.png"
        # )
        # self.ORDER_LIST_JSON_FILENAME = (
        #    self.cache["ORDER_LISTS"] / f"kjell-{self.COUNTRY}-orders.json"
        # )

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        pass

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your Polyalkemi.no orders.
        """
        try:
            #if self.options.use_cached_orderlist:
            #    if self.can_read(self.ORDER_LIST_JSON_FILENAME):
            #        return self.read(self.ORDER_LIST_JSON_FILENAME, from_json=True)
            #    else:
            #        self.log.info("Could not find cached orderlist.")
            #
                    brws = self.browser_visit_page(
                        self.ORDER_LIST_URL, default_login_detect=False
                    )
                    try:
                        login_form = brws.find_element(By.CSS_SELECTOR, "form.login")
                        self.log.error(RED("You need to login manually. Press enter when completed."))
                        input()
                        brws = self.browser_visit_page(
                            self.ORDER_LIST_URL, default_login_detect=False
                        )
                    except NoSuchElementException:
                         pass
                    orders_table = brws.find_element(By.CSS_SELECTOR, "table.woocommerce-orders-table")
                    order_rows = orders_table.find_elements(By.CSS_SELECTOR, "tbody tr")
                    for order_row in order_rows:
                         order_cols = order_row.find_elements(By.CSS_SELECTOR, "td")
                         self.log.debug("ordre: %s", order_cols[0].text)
                         self.log.debug("dato: %s", order_cols[1].text)
                         self.log.debug("status: %s", order_cols[2].text)
                         self.log.debug("total: %s", order_cols[3].text)
                    
                    # cleanup:
                    # cssselect:
                    # .elementor-location-header
                    # xpatg
                    # //h2[contains(text(), 'Tilsvarende produkter')]/ancestor::section
                    # //footer/parent::div

                    input()
        except NoSuchWindowException:
            pass
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
        super().setup_cache(Path("polyalkemi-no"))
        self.setup_templates()
