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
        if settings.SCRAPER_EBY_MANUAL_LOGIN:
            self.log.debug(
                self.command.style.ERROR(
                    "Please log in to eBay and press enter when ready."
                )
            )
            input()
            brws = self.browser_get_instance()
        else:
            brws = self.browser_get_instance(emulate_mobile_browser=True)

            title = "".join(
                random.choice(string.ascii_lowercase) for i in range(25)
            )
            time.sleep(2)
            brws.execute_script(f'document.title = "{title}"')

            if sys.platform.startswith("win32"):
                import uiautomation as auto

                window = auto.WindowControl(
                    searchDepth=1, RegexName=rf".*{title}.*"
                )
                window.SendKeys("{Ctrl}{Shift}{M}", 0.2, 0)
            # elif sys.platform.startswith("linux"):
            #    pass
            elif sys.platform.startswith("darwin"):
                self.log.info(
                    "Could not automate Responsive Design Mode activation,"
                    " please activate Responsive Design Mode in Firefox by"
                    " pressing [Cmd]-[Opt]-[m] and press enter."
                )
                input()
            else:
                self.log.info(
                    "Could not automate Responsive Design Mode activation,"
                    " please activate Responsive Design Mode in Firefox by"
                    " pressing [Ctrl]-[Shift]-[m] and press enter."
                )
                input()

            self.log.debug("Visiting order page %s", self.ORDER_LIST_URL)
            self.browser_visit_page_v2(self.ORDER_LIST_URL)

            self.rand_sleep(1, 3)
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(10)
            for item_container in self.find_elements(
                By.CSS_SELECTOR, "div.m-mweb-item-container"
            ):
                print(
                    self.find_element(
                        By.CSS_SELECTOR, "a.m-mweb-item-link", item_container
                    ).get_attribute("href")
                )
                pass

        # mobile a class m-pagination-simple-next [aria-disabled="true"]

        #
        # div.m-mweb-item-container
        #    a.m-mweb-item-link
        #    div.m-image -> img -> thumbnail
        #
        #     div.item-details
        #         div.item-banner-text -> status refunded/shippet etc
        #         h2.item-title
        #         div.item-variation (optional, SKU)
        #         div.item-info
        #             span.info-displayprice -> span BOLD, clipped (forskjell???)
        ##             span.info-logisticscost -> span or span.clipped (more info?)
        #             span.info-orderdate

        # span class filter -> span text "Last 60 Days" -> click
        # data-url: data-url="/module_provider?filter=year_filter:LAST_YEAR&page=1&modules=ALL_TRANSACTIONS&moduleId=122164" ?
        # https://www.ebay.com/mye/myebay/v2/purchase?filter=year_filter%3ALAST_YEAR&page=1&moduleId=122164&pg=purchase&mp=purchase-module-v2&type=v2
        # https://www.ebay.com/mye/myebay/v2/purchase?filter=year_filter%3ATWO_YEARS_AGO&page=1&moduleId=122164&pg=purchase&mp=purchase-module-v2&type=v2

        # <span class="m-container-message__content">No orders were found</span>
        assert brws
        # self.browser_safe_quit()

    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options, __name__)
        self.setup_cache("ebay")
        self.setup_templates()

    def command_db_to_csv(self):
        pass

    def command_load_to_db(self):
        pass

    # LXML-heavy functions
    # ...

    # Selenium-heavy function
    def browser_detect_handle_interrupt(self, expected_url):
        time.sleep(2)
        gdpr_accept = self.find_element(
            By.CSS_SELECTOR, "button#gdpr-banner-accept"
        )
        if gdpr_accept:
            self.log.debug("Accepting GDPR/cookies")
            gdpr_accept.click()
            time.sleep(0.5)
        else:
            self.log.debug("No GDPR/cookies to accept")
        if re.match(r".*captcha.*", self.browser.current_url):
            if self.find_element(By.CSS_SELECTOR, "div#captcha_loading"):
                self.log.info("Please complete captcha and press enter.")
                input()
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.browser_login(expected_url)

    def browser_login(self, expected_url):
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
                username.send_keys(src_username)
                self.rand_sleep(0, 2)
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

        if not re.match(expected_url, self.browser.current_url):
            self.log.debug(
                (
                    "Expected url was %s, but we are at %s. Press enter if you"
                    " think we can continue. Press Ctrl-Z to cancel."
                ),
                expected_url,
                self.browser.current_url,
            )
            input()
        self.log.info("Login to eBay was successful.")

    # Utility functions
    def setup_templates(self):
        # pylint: disable=invalid-name
        login_url = re.escape("https://signin.ebay.com")
        self.LOGIN_PAGE_RE = rf"{login_url}.*"
        self.ORDER_LIST_URL = "https://www.ebay.com/mye/myebay/purchase"
        self.ORDERS_CSV = self.cache["BASE"] / "order_history.csv"
        self.ITEMS_CSV = self.cache["BASE"] / "products_history.csv"
        self.ITEM_URL_TEMPLATE = "https://www.adafruit.com/product/{item_id}"
        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/order.{ext}")
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
