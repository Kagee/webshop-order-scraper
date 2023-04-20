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


class EbayScraper(BaseScraper):
    # Scrape comand and __init__

    def command_scrape(self):
        pass

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
        time.sleep(2)
        gdpr_accept = self.find_element(
            By.CSS_SELECTOR, "button#gdpr-banner-accept"
        )
        if gdpr_accept:
            self.log.debug("Accepting GDPR/cookies")
            gdpr_accept.click()
            time.sleep(0.5)

        if re.match(r".*captcha.*", self.browser.current_url):
            if self.find_element(By.CSS_SELECTOR, "div#captcha_loading"):
                self.log.info(
                    self.command.style.NOTICE(
                        "Please complete captcha and press enter: ..."
                    )
                )
                input()
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.browser_login(expected_url)

    def browser_login(self, _):
        """
        Uses Selenium to log in eBay.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required.
        """
        if settings.SCRAPER_EBY_MANUAL_LOGIN:
            self.log.debug(
                self.command.style.ERROR(
                    "Please log in to eBay and press enter when ready."
                )
            )
            input()
        else:
            # We (optionally) ask for this here and not earlier, since we
            # may not need to go live
            src_username = (
                input("Enter eBay username:")
                if not settings.SCRAPER_EBY_USERNAME
                else settings.SCRAPER_EBY_USERNAME
            )
            src_password = (
                getpass("Enter eBay password:")
                if not settings.SCRAPER_EBY_PASSWORD
                else settings.SCRAPER_EBY_PASSWORD
            )

            self.log.info(self.command.style.NOTICE("Trying to log in to eBay"))
            brws = self.browser_get_instance()

            wait = WebDriverWait(brws, 10)

            def captcha_test():
                if self.find_element(By.CSS_SELECTOR, "div#captcha_loading"):
                    self.log.info("Please complete captcha and press enter.")
                    input()

            try:
                self.rand_sleep(0, 2)
                captcha_test()
                self.log.debug("Looking for %s", "input#userid")
                username = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input#userid")
                    ),
                    "Could not find input#userid",
                )
                captcha_test()
                username.click()
                username.send_keys(src_username)
                self.rand_sleep(0, 2)
                captcha_test()
                self.log.debug("Looking for %s", "button#signin-continue-btn")
                wait.until(
                    EC.element_to_be_clickable(
                        ((By.CSS_SELECTOR, "button#signin-continue-btn"))
                    ),
                    "Could not find button#signin-continue-btn",
                ).click()
                self.rand_sleep(0, 2)

                captcha_test()
                self.log.debug("Looking for %s", "input#pass")
                password = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "input#pass")
                    ),
                    "Could not find input#pass",
                )
                self.rand_sleep(2, 2)
                captcha_test()
                password.click()
                password.send_keys(src_password)
                self.rand_sleep(0, 2)

                self.log.debug("Looking for %s", "button#sgnBt")
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "button#sgnBt"),
                    ),
                    "Could not find button#sgnBt",
                ).click()
                self.rand_sleep(0, 2)
                captcha_test()
            except TimeoutException as toe:
                # self.browser_safe_quit()
                raise CommandError(
                    "Login to eBay was not successful "
                    "because we could not find a expected element.."
                ) from toe
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.log.debug(
                "Login to eBay was not successful. If you want continue,"
                " complete login, and then press enter. Press Ctrl-Z to cancel."
            )
            input()
        self.log.info("Login to eBay was successful.")


    # Utility functions
    def setup_templates(self):
        # pylint: disable=invalid-name
        login_url = re.escape("https://signin.ebay.com")
        self.HOMEPAGE = "https://ebay.com"
        self.LOGIN_PAGE_RE = rf"{login_url}.*"
        self.ORDER_LIST_URL = "https://www.ebay.com/mye/myebay/purchase"
        self.ITEM_URL_TEMPLATE = "https://www.ebay.com/itm/{item_id}"

        self.ORDER_URL_TEMPLATE_TRANS = (
            "https://order.ebay.com/ord/show?"
            "transid={order_trans_id}&itemid={order_item_id}#/"
        )
        self.ORDER_URL_TEMPLATE = (
            "https://order.ebay.com/ord/show?orderId={order_id}#/"
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


    def setup_cache(self, base_folder: Path):
        super().setup_cache(base_folder)
        # pylint: disable=invalid-name


