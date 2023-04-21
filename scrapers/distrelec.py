import re
import time
from typing import Dict, List

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

# pylint: disable=unused-import
from . import settings
from .base import BaseScraper, PagePart
from .utils import RED, BLUE, GREEN, AMBER


# Scraper for trying out code for other scrapers
class DistrelecScraper(BaseScraper):
    def __init__(self, options: Dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        self.DOMAIN = options.domain
        #                        https:// www.elfadistrelec.no   /login
        self.LOGIN_PAGE_RE = rf"^https://{re.escape(self.DOMAIN)}/login.*"
        self.DO_CACHE_ORDERLIST = options.use_cached_orderlist
        self.setup_cache(self.DOMAIN)
        self.setup_templates()
        self.tla = "DEC"
        self.name = options.domain

    def part_to_filename(self, part: PagePart, **kwargs):
        return None

    def command_scrape(self):
        url = self.ORDER_LIST_URL_TEMPLATE

        # self.remove(self.cache["PDF_TEMP_FILENAME"])
        # url_trigger_login = "https://www.amazon.de/-/en/gp/css/order-history"
        # self.browser_visit_page(url_trigger_login, True)
        # https://www.elfadistrelec.no/my-account/order-history
        # url = "https://www.elfadistrelec.no/login"
        self.browser_visit_page_v2(url)
        # #
        # What happened?
        # This request was blocked by our security service
        # time.sleep(30)
        self.browser_safe_quit()

    def browser_detect_handle_interrupt(self, expected_url):
        time.sleep(1)

        if self.find_element(By.CSS_SELECTOR, "iframe#main-iframe"):
            self.log.error(
                AMBER("Please complete captcha and press enter: ...")
            )
            input()
        ens = self.find_element(By.CSS_SELECTOR, "button#ensCloseBanner")
        if ens:
            self.log.INFO("Closing cookie banner")
            ens.click()
            self.rand_sleep(0, 2)

        signup = self.find_element(By.CSS_SELECTOR, "button.btn-close-signup")
        if signup and signup.is_displayed():
            self.log.debug("Closing mailing list popup")
            signup.click()
            self.rand_sleep(0, 2)

        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.browser_login(expected_url)

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

    def browser_login(self, expected_url):
        brws, username_data, password_data = self.browser_setup_login_values()

        if username_data and password_data:
            username = brws.find_element(By.ID, "j_username")
            password = brws.find_element(By.ID, "j_password")
            self.rand_sleep()
            username.send_keys(username_data)
            self.rand_sleep()
            password.send_keys(password_data)

        # button type submit, class either of ...
        submit = brws.find_element(
            By.CSS_SELECTOR, "button.b-login.js-login-button"
        )
        self.rand_sleep()
        submit.click()
        try:
            WebDriverWait(brws, 10).until_not(
                EC.url_matches(self.LOGIN_PAGE_RE)
            )
        except TimeoutException:
            self.log.error("Login to %s was not successful.", self.DOMAIN)
            self.log.error(
                "If you want to continue, fix the login, and then press enter."
            )
            input()
            if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
                # pylint: disable=raise-missing-from
                raise RuntimeError(
                    f"Login to {self.DOMAIN} was not successful, "
                    "even after user interaction."
                )
        self.log.info(GREEN("Login to %s was successful."), self.DOMAIN)

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
        # first row: div.row-holder div.row-holder__item
        #  div.date/number/by/invoice/staus (span.value/total -> (span.currency + text() )
        # second row:
        #   <a href="/my-account/order-history/order-details/1006705511"
        # class="mat-button mat-button--action-red">
        # https://www.elfadistrelec.no/my-account/
        # order-history/order-details/1006705511
        # https://www.elfadistrelec.no/my-account/
        # order-history/order-details/1006705511/download/xls/ (direct download)
        # https://www.elfadistrelec.no/my-account/
        # order-history/order-details/1006705511/download/csv/ (direct download)
