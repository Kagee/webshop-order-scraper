# pylint: disable=unused-import
import csv
import re
import time
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Dict, List
import random
import string
import sys
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
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
        if False:
            pass
        else:
            brws = self.browser_get_instance(emulate_mobile_browser=True)

            # self.browser_visit_page(
            #    # self.ORDER_LIST_URL,
            #    "https://example.com/",
            #    goto_url_after_login=False,
            #    do_login=False,
            #    default_login_detect=False,
            # )
            title = "".join(
                random.choice(string.ascii_lowercase) for i in range(25)
            )
            time.sleep(2)
            brws.execute_script(f'document.title = "{title}"')
            self.log.debug("Trying stuff")
            # print(brws.service.process)
            # print(brws.service.process.pid)
            # print(brws.service.process.args)
            # print(dir(brws.service.process))

            if sys.platform.startswith("win32"):
                import uiautomation as auto

                window = auto.WindowControl(
                    searchDepth=1, RegexName=rf".*{title}.*"
                )
                window.SendKeys("{Ctrl}{Shift}{M}", 0.2, 0)
            elif sys.platform.startswith("linux"):
                pass
            elif sys.platform.startswith("darwin"):
                import atomac

                self.log.debug("Random title is %s", title)
                automator = atomac.getAppRefByBundleId("org.mozilla.firefox")
                for window in automator.windows():
                    self.log.debug("Found window with title %s", window.AXTitle)
            else:
                self.log.info(
                    "Could not automate Responsive Design Mode activation,"
                    " please activate Responsive Design Mode in Firefox and"
                    " press enter."
                )
                input()

            # time.sleep(2)
            # self.browser_safe_quit()
            # input id userid
            # button id signin-continue-btn

            # input id pass
            # button id sgnBt

            # if div id captcha_loading:
            # uiser interaction

            # https://www.ebay.com/mye/myebay/purchase
            # mobile? https://www.ebay.com/mye/myebay/purchase?pg=purchase

            # mobile a class m-pagination-simple-next [aria-disabled="true"]

            #
            # url stats with https://signin.ebay.com
            # https://www.ebay.com/mye/myebay -> login
            # https://www.ebay.com/mye/myebay/purchase?pg=purchase
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
    def browser_detect_handle_interrupt(self, url):
        pass

    def browser_login(self, _):
        """
        Uses Selenium to log in Amazon.
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
            amz_username = (
                input("Enter eBay username:")
                if not settings.SCRAPER_AMZ_USERNAME
                else settings.SCRAPER_AMZ_USERNAME
            )
            amz_password = (
                getpass("Enter eBay password:")
                if not settings.SCRAPER_AMZ_PASSWORD
                else settings.SCRAPER_AMZ_PASSWORD
            )

            self.log.info(self.command.style.NOTICE("Trying to log in to eBay"))
            brws = self.browser_get_instance()

            wait = WebDriverWait(brws, 10)
            try:
                self.rand_sleep()
                username = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_email"))
                )
                username.send_keys(amz_username)
                self.rand_sleep()
                wait.until(
                    EC.element_to_be_clickable(((By.ID, "continue")))
                ).click()
                self.rand_sleep()
                password = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_password"))
                )
                password.send_keys(amz_password)
                self.rand_sleep()
                remember = wait.until(
                    EC.presence_of_element_located((By.NAME, "rememberMe"))
                )
                remember.click()
                self.rand_sleep()
                sign_in = wait.until(
                    EC.presence_of_element_located(
                        (By.ID, "auth-signin-button")
                    )
                )
                sign_in.click()
                self.rand_sleep()

            except TimeoutException:
                self.browser_safe_quit()
                # pylint: disable=raise-missing-from
                raise CommandError(
                    "Login to Amazon was not successful "
                    "because we could not find a expected element.."
                )
        # if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):

        self.log.info("Login to eBay was successful.")

    def browser_login(self, _):
        return False

    # Utility functions
    def setup_templates(self):
        # pylint: disable=invalid-name
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
