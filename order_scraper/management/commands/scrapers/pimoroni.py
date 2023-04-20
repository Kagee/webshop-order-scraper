# pylint: disable=unused-import
import csv
import random
import re
import string
import sys
import time
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoAlertPresentException,
    NoSuchElementException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from ....models.attachement import Attachement
from ....models.order import Order
from ....models.orderitem import OrderItem
from ....models.shop import Shop
from .base import BaseScraper, PagePart


class PimoroniScraper(BaseScraper):
    # Scrape comand and __init__

    def command_scrape(self):
        # ORDER_LIST_HTML_FILENAME_TEMPLATE
        # order_list_htmls = len(
        #    list(self.cache["ORDER_LISTS"].glob("order-list-*.html"))
        # )
        # if not self.options["use_cached_orderlist"] or not self.can_read(
        #    json_filename
        # ):
        def browser_save_order_lists():
            self.browser_visit_page_v2(self.ORDER_LIST_URL)
            more_pages = True
            while more_pages:
                order_divs = self.find_elements(By.CSS_SELECTOR, "div.order")
                self.log.debug("Found %s orders on this page", len(order_divs))
                more_pages = self.find_elements(
                    By.XPATH, "//a[contains(text(),'Next ')]"
                )
                if not more_pages:
                    self.log.debug("There are no more pages")
                else:
                    self.log.debug("Going to next page")
                    more_pages.click()

        browser_save_order_lists()

    name = "Pimoroni"
    tla = "PIM"

    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options, __name__)
        self.setup_cache("pimoroni")
        self.setup_templates()
        self.browser = None
        # pylint: disable=invalid-name

    def command_db_to_csv(self):
        pass

    def command_load_to_db(self):
        pass

    # LXML-heavy functions
    # ...

    # Selenium-heavy function
    def browser_cleanup_item_page(self):
        pass
        # TODO: cleanup browser page, look at about line 927 in amazon.py
        # remove:
        # div#menu_brand_account
        # div#benefits
        # div#navigation => to ganger? dukker opp på nytt n¨år vindu rezices? mange elementer med samme id *facepalm*
        # div#currency_picker
        # footer#footer
        # div#right
        # div#search
        # section#reviews
        # section#user_photos
        # div#lightbox
        # div#WebPixelsManagerSandboxContainer
        # tag svg?

        # css-endringer
        # tag html unset --theme-font --body-font
        # tag main displaygrid -> block
        # div#description p:first-of-type -> unset font-size
        # section#gallery unset display (grid)
        # section#gallery -> img -> data-lightbox -> /cdn/shop/products/2633-01_1500x1500.jpg?v=1436978298
        #    slett alle bortsett fra siste A/IMG
        #    set max-sice på siste img til 250px, float => right + margin-left 2em
        # h1 unset font-size, litt vel stor

        # todo:
        # url-fiks fra adafruit
        # pylint: disable=unused-import

    def browser_detect_handle_interrupt(self, expected_url):
        time.sleep(1)
        country_sel: WebElement = self.find_element(
            By.XPATH, "//button[text()='Continue']"
        )
        if country_sel:
            self.log.debug("Accepting country")
            country_sel.click()
            time.sleep(0.5)

        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.browser_login(expected_url)

    def browser_login(self, _):
        """
        Uses Selenium to log in.
        """
        brws, username_data, password_data = self.browser_setup_login_values()

        if username_data and password_data:
            wait = WebDriverWait(brws, 10)
            try:
                self.rand_sleep(0, 2)
                xpath_sel = "//form[@id='customer_login']//input[@type='email']"
                self.log.debug("Looking for %s", xpath_sel)
                username = wait.until(
                    EC.presence_of_element_located((By.XPATH, xpath_sel)),
                    "Could not find " + xpath_sel,
                )
                username.click()
                username.send_keys(username_data)
                self.rand_sleep(0, 2)

                xpath_sel = (
                    "//form[@id='customer_login']//input[@type='password']"
                )
                self.log.debug("Looking for %s", xpath_sel)
                password = wait.until(
                    EC.presence_of_element_located((By.XPATH, xpath_sel)),
                    "Could not find " + xpath_sel,
                )
                password.click()
                password.send_keys(password_data)
                self.rand_sleep(0, 2)

                xpath_sel = (
                    "//form[@id='customer_login']//button[contains(@class,"
                    " 'login')]"
                )
                self.log.debug("Looking for %s", xpath_sel)
                wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, xpath_sel),
                    ),
                    "Could not find " + xpath_sel,
                ).click()
                self.rand_sleep(0, 2)

            except TimeoutException as toe:
                # self.browser_safe_quit()
                raise CommandError(
                    f"Login to {self.name} was not successful "
                    "because we could not find a expected element.."
                ) from toe
        time.sleep(2)
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.log.debug(
                (
                    "Login to %s was not successful. If you want continue,"
                    " complete login, and then press enter. Press Ctrl-Z to"
                    " cancel."
                ),
                self.name,
            )
            input()
        self.log.info("Login to %s was successful.", self.name)

    # Utility functions
    def setup_templates(self):
        # pylint: disable=invalid-name
        # https://shop.pimoroni.com/account/login?return_url=%2Faccount
        login_url = re.escape("https://shop.pimoroni.com/account/login")
        self.HOMEPAGE = "https://shop.pimoroni.com/"
        self.LOGIN_PAGE_RE = rf"{login_url}.*"
        self.ORDER_LIST_URL = "https://shop.pimoroni.com/account"
        self.ITEM_URL_TEMPLATE = "https://shop.pimoroni.com/products/{item_name}?variant={item_variant}"

        self.ORDER_LIST_HTML_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDER_LISTS"] / Path("/order-list-{page}.html")
        )
        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{key}/order.{ext}")
        )
        self.ORDER_ITEM_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/item-{item_id}.{ext}")
        )

    def part_to_filename(self, part: PagePart, **kwargs):
        template: str
        if part == PagePart.ORDER_DETAILS:
            template = self.ORDER_FILENAME_TEMPLATE
        elif part == PagePart.ORDER_ITEM:
            template = self.ORDER_ITEM_FILENAME_TEMPLATE
        return Path(template.format(**kwargs))
