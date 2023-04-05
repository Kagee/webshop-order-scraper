import base64
import datetime
import json
import math
import os
import re
import time
import urllib.request
from getpass import getpass
from pathlib import Path
from typing import Dict, Final, List
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from lxml.etree import tostring
from lxml.html.soupparser import fromstring
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from .base import BaseScraper


class AmazonScraper(BaseScraper):
    TLD: Final[str] = "test"
    LOGIN_PAGE_RE: Final[str]
    ORDER_LIST_URL_TEMPLATE: Final[str]
    ORDER_LIST_ARCHIVED_URL_TEMPLATE: Final[str]
    ORDER_URL_TEMPLATE: Final[str]
    YEARS: Final[List]
    ORDER_LIST_HTML_FILENAME_TEMPLATE: str
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
        self.ORDER_URL_TEMPLATE = \
            (f'https://www.amazon.{self.TLD}/'
            'gp/your-account/order-details/?ie=UTF8&orderID={order_id}')
        self.ITEM_URL_TEMPLATE = \
            (f'https://www.amazon.{self.TLD}/'
            '-/en/gp/product/{item_id}/?ie=UTF8')

        self.setup_cache()

    def command_scrape(self) -> None:
        order_lists_html = self.load_order_lists_html()
        order_lists = self.lxml_parse_order_lists_html(order_lists_html)
        self.save_order_lists_to_json(order_lists)
        order_lists: Dict[str, Dict] = {}
        counter = 0
        if settings.SCRAPER_AMZ_ORDERS_SKIP:
            self.log.debug("Skipping scraping order IDs: %s", settings.SCRAPER_AMZ_ORDERS_SKIP)
        if settings.SCRAPER_AMZ_ORDERS:
            self.log.debug("Scraping only order IDs: %s", settings.SCRAPER_AMZ_ORDERS)
        for year in self.YEARS:
            self.log.debug("Year: %s", year)
            order_lists[year] = self.order_list_json( year, read = True)
            for order_id in sorted(order_lists[year]):
                if order_id.startswith("D01"):
                    self.log.info(
                            "Digital orders (%s) is PITA to scrape, "
                            "so we don't support them for now", 
                            order_id)
                    continue
                if ((len(settings.SCRAPER_AMZ_ORDERS) and \
                    order_id not in settings.SCRAPER_AMZ_ORDERS)) or \
                        (order_id in settings.SCRAPER_AMZ_ORDERS_SKIP):
                    self.log.info("Skipping order ID %s", order_id)
                    continue
                counter += 1
                if settings.SCRAPER_AMZ_ORDERS_MAX > 0:
                    if counter > settings.SCRAPER_AMZ_ORDERS_MAX:
                        self.log.info(
                            "Scraped %s order(s), breaking", 
                            settings.SCRAPER_ALI_ORDERS_MAX)
                        break
                self.parse_order(order_id, order_lists[year][order_id])

        #self.browser_safe_quit()

    def parse_order(self, order_id: Dict, order: Dict):
        order_cache_dir = self.cache['ORDERS'] / Path(order_id)
        html_cache = self.ORDER_FILENAME_TEMPLATE.format(
            order_id=order_id, ext="html"
            )
        try:
            os.makedirs(order_cache_dir)
        except FileExistsError:
            pass
        if os.access(html_cache, os.R_OK):
            self.log.debug("Found HTML cache for order %s", order_id)
        else:
            self.log.debug("Did not find HTML cache for order %s", order_id)
            order.update(self.browser_scrape_order(order_id, order_cache_dir))
        self.pprint(order)

    def browser_scrape_order(self, order_id: str, order_cache_dir: Path) -> Dict:
        order = {}
        curr_url = self.ORDER_URL_TEMPLATE.format(order_id=order_id)
        self.log.debug("Scraping %s, visiting %s", order_id, curr_url)
        brws = self.browser_visit_page(curr_url, goto_url_after_login=True)
        wait2 = WebDriverWait(brws, 2)
        invoice_a = ("//a[contains(@class, 'a-popover-trigger')]"
                        "/span[contains(text(), 'Invoice')]/ancestor::a")
        order_summary_a = ("//span[contains(@class, 'a-button')]"
                        "/a[contains(text(), 'Order Summary')]")
        # Need to wait a tiny bit for the JS
        # connected to this link to load
        time.sleep(2)
        # TODO: Fix when no invoice button
        try:
            wait2.until(
                    EC.presence_of_element_located(
                        (By.XPATH,
                        invoice_a
                        )
                    ), "Timeout waiting for Invoice").click()
            self.log.debug(
                "Found Invoice button"
                )
            time.sleep(1)
            # then this should appear
            invoice_wrapper: WebElement = wait2.until(
                EC.presence_of_element_located(
                    (By.XPATH,
                    "//div[contains(@class, 'a-popover-wrapper')]"
                    )
                ), "Timeout waiting for invoice wrapper")
            elements_to_loop: List[WebElement] = \
                invoice_wrapper.find_elements(By.TAG_NAME, 'a')
        except TimeoutException:
            self.log.debug(
                "Timeout waiting for Invoice, "
                "maybe only have Order Summary"
                )
            elements_to_loop: List[WebElement] = [wait2.until(
                    EC.presence_of_element_located(
                        (By.XPATH,
                        order_summary_a
                        )
                    ), "Timeout waiting for Order Summary button")]

        order_handle = brws.current_window_handle
        order['attachements'] = []
        self.log.debug("Downloading attachements")

        for invoice_item in elements_to_loop:
            text = invoice_item.text.replace('\r\n', ' ').replace('\r', '').replace('\n', ' ')
            self.log.debug("Attachement '%s'", text)
            href = invoice_item.get_attribute('href')
            attachement = { "text": text, "href": href }

            text_filename_safe = base64.urlsafe_b64encode(
                    text.encode("utf-8")).decode("utf-8")

            attachement_file = (order_cache_dir / \
                Path(f"{order_id}-attachement-{text_filename_safe}.pdf")).resolve()

            if os.access(attachement_file, os.R_OK):
                attachement['file'] = str(Path(attachement_file)\
                    .relative_to(self.cache['BASE'])) # keep this
                order['attachements'].append(attachement)
                self.log.debug("We already have this file saved")
                continue
            order_summary = re.match(r'.+summary/print.+', href)
            download_pdf = re.match(r'.+/download/.+\.pdf', href)
            contact_link = re.match(r'.+contact/contact.+', href)

            if order_summary:
                if os.access(self.PDF_TEMP_FILENAME, os.R_OK):
                    # Remove old random temp
                    os.remove(self.PDF_TEMP_FILENAME)
                brws.switch_to.new_window()
                brws.get(href)
                self.log.debug("This is the order summary. Open, print to PDF, close.")
                self.browser.execute_script('window.print();')
                while not os.access(self.PDF_TEMP_FILENAME, os.R_OK):
                    self.log.debug("PDF file does not exist yet")
                    time.sleep(1)
                self.wait_for_stable_file(self.PDF_TEMP_FILENAME)
                attachement['file'] = str(Path(attachement_file)\
                    .relative_to(self.cache['BASE'])) # keep this
                os.rename(self.PDF_TEMP_FILENAME, attachement_file)
                brws.close()
            elif download_pdf:
                self.log.debug("This is a invoice PDF.")
                for pdf in self.PDF_TEMP_FOLDER.glob('*.pdf'):
                    # Remove old/random PDFs
                    os.remove(pdf)
                brws.switch_to.new_window()
                # Can't use .get(...) here, since Selenium appears to
                # be confused by the fact that Firefox downloads the PDF
                brws.execute_script("""
                    setTimeout(() => {
                        document.location.href = arguments[0];
                    }, "500");
                    """,
                    href
                    )
                self.log.debug("Opened pdf")
                ## Look for PDF in folder
                pdf = list(self.PDF_TEMP_FOLDER.glob('*.pdf'))
                while not pdf:
                    pdf = list(self.PDF_TEMP_FOLDER.glob('*.pdf'))
                    time.sleep(3)
                # We have a PDF, move it to  a proper name
                self.wait_for_stable_file(pdf[0])
                attachement['file'] = str(Path(attachement_file)\
                    .relative_to(self.cache['BASE'])) # keep this
                os.rename(pdf[0], attachement_file)
                brws.close()
            elif contact_link:
                self.log.warning("Contact link, nothing useful to save")
            else:
                self.log.warning(
                    self.command.style.WARNING(
                    "Unknown attachement, not saving: %s, %s"),
                      text, href)
            order['attachements'].append(attachement)
            brws.switch_to.window(order_handle)

        # Finished "scraping", save HTML to disk
        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        time.sleep(2)

        if 'items' not in order:
            order['items'] = {}
        self.log.debug("Scraping item IDs, thumbnails and pages (as PDF)")
        for item in brws.find_elements(
            By.XPATH,
            "//div[contains(@class, 'yohtmlc-item')]"
            "/parent::div"):
            item_id = None
            for atag in item.find_elements(By.TAG_NAME, 'a'):
                product_link = re.match(
                    # item id or "gc" => gift card
                    r'.+/product/(?P<id>([A-Z0-9]*|gc)).+', 
                    atag.get_attribute('href'))
                if product_link:
                    item_id = product_link.group('id')
            self.log.debug("Item id: %s", item_id)
            assert item_id
            if item_id not in order['items']:
                order['items'][item_id]= {}
            # Don't save anything for gift cards
            if item_id != 'gc':
                thumb = item.find_element(
                    By.XPATH, 
                    ".//img[contains(@class, 'yo-critical-feature')]")
                high_res_thumb_url = thumb.get_attribute("data-a-hires")
                ext = os.path.splitext(urlparse(high_res_thumb_url).path)[1]
                item_thumb_file = (order_cache_dir / \
                    Path(f"{order_id}-item-thumb-{item_id}.{ext}")).resolve()

                urllib.request.urlretrieve(high_res_thumb_url, item_thumb_file)
                order['items'][item_id]['thumbnail'] = str(Path(item_thumb_file)\
                        .relative_to(self.cache['BASE'])) # keep this

        for item_id in order['items']:

            self.log.debug("New tab")
            brws.switch_to.window(order_handle)
            brws.switch_to.new_window()
            self.log.debug("Opening item page for %s", item_id)
            brws.get(self.ITEM_URL_TEMPLATE.format(item_id=item_id))

            self.log.debug("Slowly scrolling to bottom of page")
            brws.execute_script(
                """
                var hlo_wh = window.innerHeight/2;
                var hlo_count = 0;
                var intervalID = setInterval(function() {
                    window.scrollTo(0,hlo_wh*hlo_count)
                    hlo_count = hlo_count + 1;
                    console.log(hlo_count)
                    if (hlo_count > 20) {
                        clearInterval(intervalID);
                    }
                }, 500);

                """,
                )

            # Javascript above happens async
            time.sleep(11)
            elemets_to_hide: List[WebElement] = []
            for xpath in [
                "//div[contains(@class, 'a-carousel-row')]",
                "//div[contains(@class, 'a-carousel-header-row')]",
                "//div[contains(@class, 'a-carousel-container')]",
            ]:
                elemets_to_hide += brws.find_elements(By.XPATH, xpath)

            for element_id in [
                "navFooter",
                "navbar",
                "similarities_feature_div",
                "dp-ads-center-promo_feature_div",
                "ask-btf_feature_div",
                "customer-reviews_feature_div"
            ]:
                elemets_to_hide += brws.find_elements(By.ID, element_id)

            self.log.debug("Hide flutt, ads, etc")
            self.browser.execute_script(
                """
                console.log("Hiding stuff")
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].setAttribute('style', 'display: none;');
                    arguments[0][i].style.opacity = 0;
                    arguments[0][i].style.display = "none";
                    console.log(arguments[0][i])
                }
                arguments[1].scrollIntoView()
                """,
                elemets_to_hide, brws.find_element(By.ID, 'landingImage'))
            time.sleep(1)
            self.log.debug("View and preload all item images")

            # Scroll to "top" of product listing
            ActionChains(self.browser).\
                scroll_to_element(
                brws.find_element(
                By.ID,
                'ppd')).perform()

            img_btns = brws.find_elements(
                By.XPATH,
                "//li[contains(@class,'imageThumbnail')]")
            
            for img_btn in img_btns:
                time.sleep(1)
                img_btn.click()
            img_btns[0].click()

            images = brws.find_elements(
                By.XPATH,
                "//li[contains(@class,'image')][contains(@class,'item')]//img")
            img_urls = []
            for image in images:
                highres = image.get_attribute('data-old-hires')
                if highres:
                    img_urls.append(highres)

            self.log.debug("Include all item images on bottom of page")
            self.browser.execute_script(
                """
                for (let i = 0; i < arguments[0].length; i++) {
                    var img = document.createElement('img');
                    img.src = arguments[0][i];
                    arguments[1].appendChild(img);
                    console.log(arguments[0][i])
                }
                """,
                img_urls, brws.find_element(By.ID, "dp"))
            time.sleep(2)
            self.log.debug("Printing page to PDF")
            brws.execute_script('window.print();')
            while not os.access(self.PDF_TEMP_FILENAME, os.R_OK):
                self.log.debug("PDF file does not exist yet")
                time.sleep(1)
            self.wait_for_stable_file(self.PDF_TEMP_FILENAME)
            item_pdf_file = (order_cache_dir / \
                Path(f"{order_id}-item-{item_id}.pdf")).resolve()
            order['items'][item_id]['pdf'] = str(Path(item_pdf_file)\
                .relative_to(self.cache['BASE']))
            os.rename(self.PDF_TEMP_FILENAME, item_pdf_file)
            self.log.debug("PDF moved to cache")

            brws.close()
            self.log.debug("Closed page for item %s", item_id)

        time.sleep(10)
        self.log.debug("Opening order page again")
        brws.switch_to.window(order_handle)
        #brws.get(curr_url)
        wait2.until(
        EC.presence_of_element_located(
            (By.XPATH,
            invoice_a
            )
        ), "Timeout waiting for Invoice").click()
        fname = self.ORDER_FILENAME_TEMPLATE.format(
            order_id=order_id, ext="html"
            )
        with open(fname, "w", encoding="utf-8") as html_file:
            order_html = fromstring(brws.page_source)
            html_file.write(tostring(order_html).decode("utf-8"))
            self.log.debug("Saved order page HTML to file")
        return order


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
            order_list_html[(year, start_index)] = \
                self.save_order_list_cache_html_file(year, start_index)
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
        order_list_html[(year, start_index)] = \
            self.save_order_list_cache_html_file(year, start_index)
        if num_orders <= 10:
            self.log.debug("This order list (%s) has only one page", year)
            if found_next_button:
                self.log.critical(
                    "But we found a \"Next\" button. "
                    "Don't know how to handle this...")
                raise CommandError("See critical error above")
            return False

        return found_next_button and next_button_works

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
                                raise CommandError(
                                    f"We failed to match '{txtvalue}' "
                                    "to one of id/date/total")

                            matches_dict = matches.groupdict().copy()
                            if matches.group('date1'):
                                matches_dict['date'] = \
                                    datetime.datetime.strptime(
                                    matches.group('date1'), '%d %B %Y'
                                    )

                            elif matches.group('date2'):
                                matches_dict['date'] = \
                                    datetime.datetime.strptime(
                                    matches.group('date2'), '%B %d, %Y'
                                    )

                            del matches_dict['date1']
                            del matches_dict['date2']

                            value_matches.update({k:v for (k,v) in matches_dict.items() if v})

                        if value_matches['id'] not in order_lists[year]:
                            order_lists[year][value_matches['id']] = {"items": {}}

                        order_lists[year][value_matches['id']]['total'] = value_matches['total']

                        order_lists[year][value_matches['id']]['date']= value_matches['date']
                        self.log.info(
                            "Order ID %s, %s, %s", 
                            value_matches['id'],
                            value_matches['total'],
                            value_matches['date'].strftime('%Y-%m-%d'))
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
        cache_file = self.ORDER_LIST_HTML_FILENAME_TEMPLATE.format(
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
                            self.ORDER_LIST_HTML_FILENAME_TEMPLATE.format(
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

        self.log.info(
            "Found HTML cache for order list: %s", 
            ", ".join([str(x) for x in self.YEARS if x not in missing_years]))
        self.log.info(
            "Found JSON cache for order list: %s", 
            ", ".join([str(x) for x in json_cache]))
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
                more_pages = \
                    self.browser_scrape_individual_order_list_page(
                    year,
                    start_index,
                    order_list_html)
                start_index += 10
                self.rand_sleep()
        return order_list_html

    def browser_login(self, _):
        '''
        Uses Selenium to log in Amazon.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required.
        '''
        if settings.SCRAPER_AMZ_MANUAL_LOGIN:
            self.log.debug(
                self.command.style.ERROR(
                f"Please log in to amazon.{self.TLD} and press enter when ready."))
            input()
        else:
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

    def setup_cache(self):
        # pylint: disable=invalid-name
        self.cache: Dict[str, Path] = {
            "BASE": (Path(settings.SCRAPER_CACHE_BASE) / 
                     Path(f'amazon_{self.TLD.replace(".","_")}')).resolve()
        }
        self.cache.update({
            "ORDER_LISTS":  (self.cache['BASE'] / 
                             Path('order_lists')).resolve(),
            "ORDERS":  (self.cache['BASE'] / 
                        Path('orders')).resolve(),
        })

        for key in self.cache:  # pylint: disable=consider-using-dict-items
            self.log.debug("Cache folder %s: %s", key, self.cache[key])
            try:
                os.makedirs(self.cache[key])
            except FileExistsError:
                pass

        self.PDF_TEMP_FOLDER: Path = self.cache['BASE'] / Path('temporary-pdf/')
        try:
            os.makedirs(self.PDF_TEMP_FOLDER)
        except FileExistsError:
            pass

        self.PDF_TEMP_FILENAME: Path = self.PDF_TEMP_FOLDER / Path('temporary-pdf.pdf')

        self.ORDER_LIST_HTML_FILENAME_TEMPLATE: Path = \
            str(self.cache["ORDER_LISTS"] / Path("order-list-{year}-{start_index}.html"))
        self.ORDER_LIST_JSON_FILENAME_TEMPLATE: Path = \
            str(self.cache["ORDER_LISTS"] / Path("order-list-{year}.json"))
        self.ORDER_FILENAME_TEMPLATE: Path = \
            str(self.cache["ORDERS"] / Path("{order_id}/order-{order_id}.{ext}"))

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
        return {}

    def order_json(self, order_id, read = False) -> Dict:
        fname = self.ORDER_FILENAME_TEMPLATE.format(
            order_id=order_id, ext="html"
            )
        if os.access(fname,os.R_OK):
            if not read:
                return True
            with open(fname, "r", encoding="utf-8") as json_file:
                return json.load(json_file)
        return None
    