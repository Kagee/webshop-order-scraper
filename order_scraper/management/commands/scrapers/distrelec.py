# pylint: disable=unused-import
import os
import re
import time
from pathlib import Path
from typing import Dict, List
from lxml.etree import tostring
from lxml.html.soupparser import fromstring
from django.conf import settings
from django.core.management.base import BaseCommand
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from .base import BaseScraper, PagePart


# Scraper for trying out code for other scrapers
class DistrelecScraper(BaseScraper):
    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options, __name__)
        # pylint: disable=invalid-name
        self.DOMAIN = options["domain"]
        self.LOGIN_PAGE_RE = rf"^https://{re.escape(self.DOMAIN)}/login.+"
        self.DO_CACHE_ORDERLIST = options["cache_orderlist"]
        self.setup_cache(self.DOMAIN)
        self.setup_templates()

    def part_to_filename(self, part: PagePart, **kwargs):
        return None

    def command_scrape(self):
        url = self.ORDER_LIST_URL_TEMPLATE

        # self.remove(self.cache["PDF_TEMP_FILENAME"])
        # url_trigger_login = "https://www.amazon.de/-/en/gp/css/order-history"
        # self.browser_visit_page(url_trigger_login, True)
        # https://www.elfadistrelec.no/my-account/order-history
        self.browser_visit_page(url, False)

        # time.sleep(30)
        self.browser_safe_quit()

    def setup_templates(self):
        # pylint: disable=invalid-name
        # URL Templates
        self.ORDER_LIST_URL_TEMPLATE = (
            f"https://{self.DOMAIN}/my-account/order-history"
        )

    def browser_cleanup_item_page(self):
        brws = self.browser
        self.log.debug("Hide fluff, ads, etc")
        elemets_to_hide: List[WebElement] = []
        for element in []:
            elemets_to_hide += brws.find_elements(element[0], element[1])
        brws.execute_script(
            """
                // remove spam/ad elements
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].remove()
                }
                """,
            elemets_to_hide,
        )
        time.sleep(2)

    def browser_login(self, url):
        if settings.HLO_SCRAPER_DEC_MANUAL_LOGIN:
            self.log.debug(
                self.command.style.ERROR(
                    f"Please log in to {self.DOMAIN} and press enter when"
                    " ready."
                )
            )
            input()
        else:
            pass
        # input id j_password
        # input id j_username
        # button type submit, class either of b-login js-login-button

        # tag nav class mod-servicenav
        # span class language
        #    => if TEXT -> EN, great, nothing to do
        # else -> hover over same span
        # tag section class flyout-settings
        #     select id select-language
        #     option value en, text English -> click
        #     input type submit
        # page reloads in english

        # len (a class js-page-link) => number of order pages
        # span id select-productlist-paginationSelectBoxItText -> text() => items per order page

        # each item in container -> div.row-holder
        #  -> two row-holder__item
        # first row: div.row-holder div.row-holder__item div.date/number/by/invoice/staus (span.value/total -> (span.currency + text() )
        # second row:
        #   <a href="/my-account/order-history/order-details/1006705511" class="mat-button mat-button--action-red">
        # https://www.elfadistrelec.no/my-account/order-history/order-details/1006705511
        # https://www.elfadistrelec.no/my-account/order-history/order-details/1006705511/download/xls/ (direct download)
        # https://www.elfadistrelec.no/my-account/order-history/order-details/1006705511/download/csv/ (direct download)

    def browser_login2(self, _):
        """
        Uses Selenium to log in Amazon.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required.
        """
        if settings.SCRAPER_AMZ_MANUAL_LOGIN:
            pass
        else:
            # We (optionally) ask for this here and not earlier, since we
            # may not need to go live
            self.username = settings.SCRAPER_AMZ_USERNAME
            self.password = settings.SCRAPER_AMZ_PASSWORD

            self.log.info(
                self.command.style.NOTICE("We need to log in to amazon.%s"),
                "de",
            )
            brws = self.browser_get_instance()

            wait = WebDriverWait(brws, 10)
            try:
                self.rand_sleep()
                username = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_email"))
                )
                username.send_keys(self.username)
                self.rand_sleep()
                wait.until(
                    EC.element_to_be_clickable(((By.ID, "continue")))
                ).click()
                self.rand_sleep()
                password = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_password"))
                )
                password.send_keys(self.password)
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
                print(
                    "Login to Amazon was not successful "
                    "because we could not find a expected element.."
                )
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            print("Login to Amazon was not successful.")
        self.log.info("Login to Amazon was probably successful.")
