# pylint: disable=unused-import
import base64
from decimal import Decimal
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Union
from urllib.parse import urlparse, urlencode, parse_qs
import requests
import filetype

from selenium.common.exceptions import (
    NoSuchElementException,
    NoSuchWindowException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from . import settings
from .base import BaseScraper

# pylint: disable=unused-import
from .utils import AMBER, BLUE, GREEN, RED


class KomplettScraper(BaseScraper):
    tla: Final[str] = "KMP"
    name: Final[str] = "Komplett"
    simple_name: Final[str] = "komplett"

    def __init__(self, options: Dict):
        super().__init__(options, __name__)
        self.setup_cache(self.simple_name)
        self.setup_templates()

    def command_scrape(self):
        if self.options.use_cached_orderlist and self.can_read(self.ORDER_LIST_JSON):
            order_dict = self.read(self.ORDER_LIST_JSON, from_json=True)
        else:
            order_dict = {}
            brws = self.browser_visit("https://www.komplett.no/orders")
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(1)
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(1)
            show_more: WebElement = self.find_element(By.XPATH, "//span[normalize-space(text())='Vis mer']")
            while show_more and show_more.is_displayed():
                show_more.click()
                time.sleep(1)
                brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                time.sleep(1)
                brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                show_more: WebElement = self.find_element(By.XPATH, "//span[normalize-space(text())='Vis mer']")
            order_number_elements: List[WebElement] = self.find_elements(By.XPATH, "//section[contains(@class, 'tidy-orders-list')]/article/table/tbody/tr/td[contains(@class, 'order-number')]/a")
            
            for order_number_element in order_number_elements:
                order_dict[order_number_element.text.strip()] = {}
            
            for order_id,order_dict in order_dict.items():
                if order_id != "200633800":
                    continue
                # nyeste: 204547164
                # tre items, 200633800
                # siste: 15478583
                self.log.debug("Scraping order id %s", order_id)
                self.browser_visit(f"https://www.komplett.no/orders/{order_id}")
                input()
                break


    def browser_detect_handle_interrupt(self, expected_url):
        brws = self.browser_get_instance()
        if 'login' in brws.current_url:
            self.log.info(AMBER("Please log in to Komplett. Press <ENTER> when finished."))
            input()
            self.browser_visit(expected_url)


    def command_to_std_json(self):
        structure = self.get_structure(
            self.name,
            None,
            "https://www.adafruit.com/index.php"
            "?main_page=account_history_info&order_id={order_id}",
            "https://www.adafruit.com/product/{item_id}",
        )
        
        self.output_schema_json(structure)

  
    def setup_templates(self):
        # pylint: disable=invalid-name
        self.ORDER_LIST_JSON = self.cache["BASE"] / "order_list.json"
        self.ORDERS = self.cache["BASE"] / "products_history.csv"
        self.ITEM_URL_TEMPLATE = "https://www.adafruit.com/product/{item_id}"
        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/order.{ext}")
        )
        self.ORDER_ITEM_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/item-{item_id}.{ext}")
        )
