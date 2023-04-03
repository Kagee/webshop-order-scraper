import datetime
import json
import math
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
    # Xpath to individual order item parent element
    ORDER_CARD_XPATH: Final[str] = \
        "//div[contains(@class, 'js-order-card')]"
    years: list

    def __init__(self, command: BaseCommand, options: Dict, archived = 'There are no'):
        super().__init__(command, options)

        self.log = self.setup_logger(__name__)
        self.command = command
        self.archived = archived
        self.cache_orderlist = options['cache_orderlist']

        # pylint: disable=invalid-name
        self.TLD = self.check_tld(options['tld'])
        self.YEARS = self.check_year(
            options['year'],
            options['start_year'],
            options['not_archived'])

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

        (self.cache,
         self.PDF_TEMP_FILENAME,
         self.ORDER_LIST_CACHE_FILENAME_TEMPLATE,
         self.ORDER_LIST_JSON_FILENAME_TEMPLATE) = self.setup_cache()

    def command_scrape(self) -> None:
        order_lists_html = self.load_order_lists_html()
        order_lists = self.lxml_parse_order_lists_html(order_lists_html)
        self.save_order_lists_to_json(order_lists)
        self.browser_safe_quit()


    def lxml_parse_order_lists_html(self, order_lists_html: Dict) -> None:
        order_lists = {}
        if order_lists_html:
            for key in order_lists_html:
                html = order_lists_html[key]
                year, _ = key
                order_card = html.xpath(self.ORDER_CARD_XPATH)
                # There are not items on this page
                if len(order_card) == 0:
                    order_lists[year] = {}
                    self.log.info("%s has no orders, returning empty dict", year)
                else:
                    if year not in order_lists:
                        order_lists[year] = {}
                    for order_card in order_card:
                        values = order_card.xpath(".//span[contains(@class, 'value')]")
                        
                        value_matches = {"date": None, "id": None, "total": None}
                        for value in values:
                            txtvalue = "".join(value.itertext()).strip()
                            matches = re.match(
                                r'(?P<date1>^\d+ .+ \d\d\d\d$)|' \
                                r'(?P<date2>.+ \d+, \d\d\d\d$)|' \
                                r'(?P<id>[0-9D]\d\d-.+)|'\
                                r'(?P<total>.*\d+(,|\.)\d+.*)', 
                                txtvalue)
                            if not matches:
                                raise CommandError(f"We failed to match '{txtvalue}' to one of id/date/total")

                            matches_dict = matches.groupdict().copy()
                            if matches.group('date1'):
                                matches_dict['date'] = datetime.datetime.strptime(matches.group('date1'), '%d %B %Y')

                            elif matches.group('date2'):
                                matches_dict['date'] = datetime.datetime.strptime(matches.group('date2'), '%B %d, %Y')
                            
                            del matches_dict['date1']
                            del matches_dict['date2']

                            value_matches.update({k:v for (k,v) in matches_dict.items() if v})
                      
                        if value_matches['id'] not in order_lists[year]:
                            order_lists[year][value_matches['id']] = {"items": {}}
                        
                        order_lists[year][value_matches['id']]['total'] = value_matches['total']
                        
                        order_lists[year][value_matches['id']]['date']= value_matches['date']
                        self.log.info("Order ID %s, %s, %s", value_matches['id'], value_matches['total'],  value_matches['date'].strftime('%Y-%m-%d'))
        else:
            self.log.info("No order HTML to parse")
        return order_lists



    def save_order_list_cache_html_file(self, year, start_index):
        json_file = \
                self.ORDER_LIST_JSON_FILENAME_TEMPLATE.format(year=year)
        # If we are saving a new HTML cache, invalidate possible json
        try:
            os.remove(json_file)
            self.log.debug("Removed json cache for %s", year)
        except FileNotFoundError:
            pass
        cache_file = self.ORDER_LIST_CACHE_FILENAME_TEMPLATE.format(
            year=year,
            start_index=start_index
            )
        self.log.info("Saving cache to %s and "
                        "appending to html list", cache_file)
        self.rand_sleep()
        return self.save_page_to_file(cache_file)

    def load_order_lists_html(self) -> Dict[int, str]:  # FIN
        '''
        Returns the order list html, eithter from disk
        cache or using Selenium to visit the url.

            Returns:
                order_list_html (List[str]): A list of the HTML from the order list pages
        '''
        order_list_html = {}
        missing_years = []
        self.log.debug("Looking for %s", ", ".join(str(x) for x in self.YEARS))
        missing_years = self.YEARS.copy()
        json_cache = []
        if self.cache_orderlist:
            self.log.debug("Checking orderlist caches")
            for year in self.YEARS:
                self.log.debug("Looking for cache of %s", str(year).capitalize())
                found_year = False
                if self.order_list_json(year):
                    self.log.debug("%s already has json", str(year).capitalize())
                    json_cache.append(year)
                    found_year = True
                else:
                    start_index = 0
                    more_pages_this_year = True
                    while more_pages_this_year:
                        html_file = \
                            self.ORDER_LIST_CACHE_FILENAME_TEMPLATE.format(
                            year=year,
                            start_index=start_index
                            )
                        self.log.debug("Looking for cache in: %s", html_file)
                        if os.access(html_file, os.R_OK):
                            found_year = True
                            self.log.debug("Found cache for %s, index %s", year, start_index)
                            with open(html_file, "r", encoding="utf-8") as olf:
                                order_list_html[(year, start_index)] = fromstring(olf.read())
                            start_index += 10
                        else:
                            more_pages_this_year = False

                if found_year:
                    missing_years.remove(year)

        self.log.info("Found HTML cache for order list: %s", ", ".join([str(x) for x in self.YEARS if x not in missing_years]))
        self.log.info("Found JSON cache for order list: %s", ", ".join([str(x) for x in json_cache]))
        if missing_years:
            self.log.info("Missing HTML cache for: %s", ", ".join(str(x) for x in missing_years))
            order_list_html.update(self.browser_scrape_order_lists(missing_years))
        return order_list_html

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

    # Function primarily using Selenium to scrape websites

    def browser_scrape_individual_order_list_page(self, year, start_index, order_list_html):
        '''
        Returns False when there are no more pages
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
    
        try:    
            wait2.until(
                EC.presence_of_element_located(
                    (By.XPATH,
                    self.ORDER_CARD_XPATH
                    )
                ))
            # If we found any order items 
            # the order list is not empty
            empty_order_list = False
        except TimeoutException:
            pass

        if empty_order_list:
            # Empty order list, shotcut and save
            self.log.info("No orders on %s", year)
            order_list_html[(year, start_index)] = self.save_order_list_cache_html_file(year, start_index)
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
        order_list_html[(year, start_index)] = self.save_order_list_cache_html_file(year, start_index)
        if num_orders <= 10:
            self.log.debug("This order list (%s) has only one page", year)
            if found_next_button:
                self.log.critical(
                    "But we found a \"Next\" button. "
                    "Don't know how to handle this...")
                raise CommandError("See critical error above")
            return False

        return found_next_button and next_button_works

    def browser_scrape_order_lists(self, years: List):
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
                more_pages = self.browser_scrape_individual_order_list_page(year, start_index, order_list_html)
                start_index += 10
                self.rand_sleep()
        return order_list_html

    def browser_login(self, _):  # Optinal manual login?
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

    # Init / Utility Functions

    def setup_cache(self):  # FIN
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

    def check_year(self, opt_years, start_year, not_archived):  # FIN
        years = list()
        if opt_years and start_year:
            self.log.error("cannot use both --year and --start-year")
            raise CommandError("cannot use both --year and --start-year")
        if opt_years:
            opt_years = sorted(set(int(year) for year in opt_years.split(",")))
            if any(year > datetime.date.today().year or year < 1990 for year in opt_years):
                err = f"one or more years in --year is in the future or " \
                        f"to distant past: {', '.join(str(year) for year in opt_years)}"
                self.log.error(err)
                raise CommandError(err)
            years = opt_years
        elif start_year:
            if start_year > datetime.date.today().year or start_year < 1990:
                err = f"The year in --start-year is in the future or to distant past: {start_year}"
                self.log.error(err)
                raise CommandError(err)
            years = sorted(range(start_year, datetime.date.today().year+1))
        else:
            years = [datetime.date.today().year]
        log_msg = f"Will scrape {', '.join(str(year) for year in years)}"
        if not not_archived:
            log_msg += " and archived orders"
            years.append("archived")
        else:
            log_msg += " and not archived orders"

        self.log.info(log_msg)
        return years

    def check_tld(self, tld):  # FIN
        statuses = {
            0: "Tested. Should work fine.",
            1: "Will probably work with zero or minor monifications.",
            2: "Formerly souq.com, modifications may be required.",
            3: "Formerly joyo.com, modifications may be required.",
            4: "Unknown Amazon TLD, totally unknown if it will work or not.",
        }
        # https://en.wikipedia.org/wiki/Amazon_(company)#Amazon.com
        amazones = {
         "at": ("Austria (redirects to amazon.de)", 0),
        "de": ("Germany", 0),
        "com": ("United States", 0),
        "co.uk": ("United Kingdom", 0),
        "co.jp": ("Japan", 0),
        "es": ("Spain", 0),
        "se": ("Sweden", 0),
               
        "com.br": ("Brazil", 1),
        "ca": ("Canada", 1),
        "com.mx": ("Mexico", 1),
        "in": ("India", 1),
        "sg": ("Singapore", 1),
        "tr": ("Turkey", 1),
        "com.be": ("Belgium", 1),
        "fr": ("France", 1),
        "it": ("Italy", 1),
        "nl": ("Netherlands", 1),
        "pl": ("Poland", 1),
        "au": ("Australia", 1),

        "cn": ("China", 2),

        "eg": ("Egypt", 3),
        "sa": ("Saudi Arabia", 3),
        "ae": ("United Arab Emirates", 3),
        }
        if tld not in amazones:
            self.log.error(self.command.style.ERROR("Site: amazon.%s. %s"), tld, statuses[4])
        elif amazones[tld][1] in [2,3]:
            self.log.warning(self.command.style.NOTICE("Site: amazon.%s. %s. %s"),
                          tld, amazones[tld][0],
                          statuses[amazones[tld][1]])
        elif amazones[tld][1] == 1:
            self.log.warning(self.command.style.WARNING("Site: amazon.%s. %s. %s"),
                          tld, amazones[tld][0],
                          statuses[amazones[tld][1]])
        else:
            self.log.info(self.command.style.SUCCESS("Site: amazon.%s. %s. %s"),
                          tld, amazones[tld][0],
                          statuses[amazones[tld][1]])
        return tld

    def order_list_json(self, year, read = False) -> Dict:
        fname = self.ORDER_LIST_JSON_FILENAME_TEMPLATE.format(
            year=year
            )
        if os.access(fname,os.R_OK):
            if not read:
                return True
            with open(fname, "r", encoding="utf-8") as json_file:
                return json.load(json_file)
        return None
