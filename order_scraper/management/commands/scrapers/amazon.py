import datetime
import json
import math
import sys
import os
import re
from getpass import getpass
from pathlib import Path
from typing import Dict, Final, List

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from lxml.html.soupparser import fromstring
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from .base import BaseScraper


class AmazonScraper(BaseScraper):
    TLD: Final[str] = "test"
    LOGIN_PAGE_RE: Final[str]
    ORDER_LIST_URL_TEMPLATE: Final[str]
    ORDER_LIST_ARCHIVED_URL_TEMPLATE: Final[str]
    ORDER_DETAIL_URL_TEMPLATE: Final[str]
    YEARS: Final[List]
    ORDER_LIST_CACHE_FILENAME_TEMPLATE: str
    ORDER_LIST_JSON_FILENAME_TEMPLATE: str
    PDF_TEMP_FILE: str
    EMPTY_ORDER_PATH_XPATH: Final[str] = \
        '//div' \
            '[contains(@class, "a-text-center")]' \
                '[contains(@class, "a-section")]'

    def __init__(self, command: BaseCommand, tld: str, options: Dict, archived = 'There are no'):
        super().__init__(command, options)

        self.log = self.setup_logger(__name__)
        self.command = command
        self.archived = archived
        self.cache_orderlist = options['cache_orderlist']

        # pylint: disable=invalid-name
        self.TLD = tld
        self.LOGIN_PAGE_RE = fr'^https://www\.amazon\.{self.TLD}/ap/signin'
        self.ORDER_LIST_URL_TEMPLATE = \
            (f'https://www.amazon.{self.TLD}/gp/css/order-history?'
                'orderFilter=year-{year}&startIndex={start_index}')
        self.ORDER_LIST_ARCHIVED_URL_TEMPLATE = \
            (f'https://www.amazon.{self.TLD}/gp/your-account/order-history'
                '?&orderFilter=archived&startIndex={start_index}')
        # The double {{order_id}} is intentional
        self.ORDER_DETAIL_URL_TEMPLATE = \
            f'https://www.amazon.{self.TLD}/your-account/order-details?ie=UTF8&orderID={{order_id}}'

        options['year'] = [int(x) for x in options['year'].split(",")]
        if options['year'] != [-1] and \
            any((x > datetime.date.today().year or x < 2011) for x in options['year']):
            self.log.critical(
                "--year must be from %s to %s inclusive, or -1",
                2011, datetime.date.today().year)
            raise CommandError("Invalid --year")

        if options['year'] == [-1]:
            self.YEARS    = list(range(2011, datetime.date.today().year))
        else:
            self.YEARS = sorted(options['year'])
        if options['archived']:
            self.YEARS.append("archived")
        (self.cache,
         self.PDF_TEMP_FILENAME,
         self.ORDER_LIST_CACHE_FILENAME_TEMPLATE,
         self.ORDER_LIST_JSON_FILENAME_TEMPLATE) = self.setup_cache()


    def setup_cache(self):
        cache = {
            "BASE": (Path(settings.SCRAPER_CACHE_BASE) / 
                     Path(f'amazon_{self.TLD.replace(".","_")}')).resolve()
        }
        cache.update({
            "ORDER_LISTS":  (cache['BASE'] / 
                             Path('order_lists')).resolve(),
            "ORDERS":  (cache['BASE'] / 
                        Path('orders')).resolve(),
        })
        for key in cache:  # pylint: disable=consider-using-dict-items
            self.log.debug("Cache folder %s: %s", key, cache[key])
            try:
                os.makedirs(cache[key])
            except FileExistsError:
                pass

        pdf_temp_file = cache['BASE'] / Path('temporary-pdf.pdf')
        order_list_cache_filename_template = \
            str(cache["ORDER_LISTS"] / Path("order-list-{year}-{start_index}.html"))
        order_list_year_json_template = \
            str(cache["ORDER_LISTS"] / Path("order-list-{year}.json"))
        return cache, \
            pdf_temp_file, \
                order_list_cache_filename_template, \
                    order_list_year_json_template

    def load_order_lists_html(self) -> Dict[int, str]:
        '''
        Returns the order list html, eithter from disk
        cache or using Selenium to visit the url.

            Returns:
                order_list_html (List[str]): A list of the HTML from the order list pages
        '''
        order_list_html = {}
        missing_years = []
        self.log.debug("Looking for %s", ", ".join(str(x) for x in self.YEARS))
        for year in self.YEARS:
            found_year = False
            if self.order_list_has_json(year) and self.cache_orderlist:
                self.log.debug("%s already has json", str(year).capitalize())
                found_year = True
            elif self.cache_orderlist:
                start_index = 0
                while True:
                    html_file = \
                        self.ORDER_LIST_CACHE_FILENAME_TEMPLATE.format(
                        year=year,
                        start_index=start_index
                        )
                    self.log.debug("Looking for cache in: %s", html_file)
                    if os.access(html_file, os.R_OK):
                        found_year = True
                        self.log.debug("Found cache %s, index %s", year, start_index)
                        with open(html_file, "r", encoding="utf-8") as olf:
                            order_list_html[(year, start_index)] = fromstring(olf.read())
                        start_index += 10
                    else:
                        break

            if not found_year:
                self.log.error("Tried to use order list cache "
                               "for %s, but found none", year)
                missing_years.append(year)

        if missing_years:
            order_list_html.update(self.browser_scrape_order_lists_html(missing_years))
            return order_list_html
        else:
            self.log.debug("Found cache for all: %s", ", ".join(str(x) for x in self.YEARS))
        return order_list_html

    def browser_login(self, _):
        '''
        Uses Selenium to log in Amazon.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required.
        '''
        # We (optionally) ask for this here and not earlier, since we
        # may not need to go live
        self.username = input(f"Enter Amazon.{self.TLD} username: ") \
                if not settings.SCRAPER_AMZ_USERNAME else settings.SCRAPER_AMZ_USERNAME
        self.password = getpass(f"Enter Amazon.{self.TLD} password: ") \
                if not settings.SCRAPER_AMZ_PASSWORD else settings.SCRAPER_AMZ_PASSWORD

        self.log.info(self.command.style.NOTICE("We need to log in to amazon.%s"), self.TLD)
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
                    EC.element_to_be_clickable(
                        ((By.ID, "continue"))
                        )
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
                    EC.presence_of_element_located((By.ID, "auth-signin-button"))
                    )
            sign_in.click()
            self.rand_sleep()

        except TimeoutException:
            self.browser_safe_quit()
            # pylint: disable=raise-missing-from
            raise CommandError("Login to Amazon was not successful "
                               "because we could not find a expected element..")
        if re.match(self.LOGIN_PAGE_RE ,self.browser.current_url):
            raise CommandError('Login to Amazon was not successful.')
        self.log.info('Login to Amazon was probably successful.')

    def order_list_has_json(self, year):
        return os.access(
            self.ORDER_LIST_JSON_FILENAME_TEMPLATE.format(
            year=year
            ),
            os.R_OK)

    def save_order_lists_to_json(self, order_lists: Dict) -> None:
        for year in order_lists:
            json_file = \
                self.ORDER_LIST_JSON_FILENAME_TEMPLATE.format(year=year)
            with open(json_file, "w", encoding="utf-8") as jsonfile:
                json_string = json.dumps(
                    order_lists[year],
                    indent=4,
                    cls=DjangoJSONEncoder
                    )
                jsonfile.write(json_string)
                self.log.debug("Saved %s", json_file)

    def command_scrape(self) -> None:
        order_lists_html = self.load_order_lists_html()
        for key in order_lists_html:
            print(key)
        return
        order_lists = self.lxml_parse_order_lists_html(order_lists_html)
        self.save_order_lists_to_json(order_lists)
        self.browser_safe_quit()

    def lxml_parse_order_lists_html(self, order_lists_html: Dict) -> None:
        order_lists = {}
        if order_lists_html:
            for key in order_lists_html:
                html = order_lists_html[key]
                # TODO: Detekter tomme archive-html riktig
                empty_list = html.xpath(self.EMPTY_ORDER_PATH_XPATH)
                if len(empty_list) == 1:
                    order_lists[key] = {}
                    self.log.debug("%s has not orders, returning empty dict", key)
                    # This order page is empty
                else:
                    # TODO: Scrape order pages with items with LXML
                    self.log.debug("%s has orders, but we do not know how to scrape them", key)
        else:
            self.log.debug("No order HTML to parse")
        return order_lists

    def save_cache_file(self, year, start_index):
        cache_file = self.ORDER_LIST_CACHE_FILENAME_TEMPLATE.format(
            year=year,
            start_index=start_index
            )
        self.log.info("Saving cache to %s and "
                        "appending to html list", cache_file)
        self.rand_sleep()
        return self.save_page_to_file(cache_file)

    def browser_scrape_order_list_page(self, year, start_index, order_list_html):
        '''
        Returns False when there are no more pages?
        '''
        self.log.debug("Scraping order list for %s, index %s", year, start_index)
        if year != "archived":
            curr_url = self.ORDER_LIST_URL_TEMPLATE.format(
                year=year,
                start_index=start_index
                )
        else:
            curr_url = self.ORDER_LIST_ARCHIVED_URL_TEMPLATE.format(
                year=year,
                start_index=start_index
                )
        self.log.debug("Visiting %s", curr_url)
        brws = self.browser_visit_page(curr_url, goto_url_after_login=True)
        wait2 = WebDriverWait(brws, 2)

        empty_order_list = True

        if year == 'archived':
            # Apparently we always find this on archived order lists
            maybe_empty_order = wait2.until(
                    EC.presence_of_element_located(
                        (By.XPATH,
                        self.EMPTY_ORDER_PATH_XPATH
                        )
                    ))
            if self.archived in maybe_empty_order.text:
                empty_order_list = True
                self.log.info("No archived orders")
            else:
                empty_order_list = False

        else:
            try:
                # On a normal order list, if we find this,
                # the order list is empty
                wait2.until(
                    EC.presence_of_element_located(
                        (By.XPATH,
                        self.EMPTY_ORDER_PATH_XPATH
                        )
                    ))
            except TimeoutException:
                # This trigger if we *don't* find the element,
                # indicating a non-empty normal order list
                empty_order_list = False

        if empty_order_list:
            self.log.info("No orders on %s", year)
            order_list_html[(year, start_index)] = self.save_cache_file(year, start_index)
            return False

        # Non-empty order page
        self.log.debug("Page %s has orders", curr_url)
        try:
            num_orders = brws.find_element(By.XPATH,
                            "//span[contains(@class, 'num-orders')]"
                            )
            num_orders: int = int(re.match(r'^(\d+)', num_orders.text).group(1))
        except NoSuchElementException:
            num_orders = 0

        self.log.debug(
            "Total of %s orders, probably %s page(s)", 
            num_orders, math.ceil(num_orders/10))

        found_next_button = False
        next_button_works = False
        try:
            next_button = brws.find_element(By.XPATH,
                        "//li[contains(@class, 'a-last')]"
                        )
            found_next_button = True
            next_button.find_element(By.XPATH,
                        ".//a"
                        )
            next_button_works = True
        except NoSuchElementException:
            pass
        order_list_html[(year, start_index)] = self.save_cache_file(year, start_index)
        if num_orders <= 10:
            self.log.debug("This order list (%s) has only one page", year)
            if found_next_button:
                self.log.critical(
                    "But we found a \"Next\" button. "
                    "Don't know how to handle this...")
                sys.exit()
            return False

        return found_next_button and next_button_works

    def browser_scrape_order_lists_html(self, years: List):
        '''
        Uses Selenium to visit, load, save and then
        return the HTML from the order list page

            Returns:
                order_lists_html (Dict[str]): A list of the HTML from the order list pages
        '''
        self.log.debug("Scraping %s using Selenium", ", ".join(str(x) for x in years))
        order_list_html = {}
        for year in years:
            more_pages = True
            start_index = 0
            while more_pages:
                more_pages = self.browser_scrape_order_list_page(year, start_index, order_list_html)
                start_index += 10
                self.rand_sleep()
        return order_list_html
