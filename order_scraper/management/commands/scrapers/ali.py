import base64
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, Final, List
from urllib.parse import urlparse

from django.conf import settings
# This is used in a Django command
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from lxml.etree import tostring
from lxml.html import HtmlElement
from lxml.html.soupparser import fromstring
from selenium import webdriver
from selenium.common.exceptions import (ElementClickInterceptedException,
                                        NoAlertPresentException,
                                        NoSuchWindowException,
                                        StaleElementReferenceException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.firefox import \
    GeckoDriverManager as FirefoxDriverManager  # type: ignore

from .base import BaseScraper


class AliScraper(BaseScraper):
    ORDER_URL: Final[str] = 'https://www.aliexpress.com/p/order/index.html'
    ORDER_DETAIL_URL: Final[str] = 'https://www.aliexpress.com/p/order/detail.html?orderId={}'
    ORDER_TRACKING_URL: Final[str] = 'https://track.aliexpress.com/logisticsdetail.htm?tradeId={}'
    previous_orders: List
    #order_list_html: str
    log = logging.getLogger(__name__)

    def __init__(self, command: BaseCommand, try_file: bool = False):
        super().__init__(command, try_file)

        self.command = command
        self.cache = {
            "BASE": (Path(settings.SCRAPER_CACHE_BASE) / 
                     Path('aliexpress')).resolve(),
            "TRACKING":  (Path(settings.SCRAPER_CACHE_BASE) / 
                          Path('aliexpress') / Path('tracking')).resolve(),
            "ORDERS":  (Path(settings.SCRAPER_CACHE_BASE) / 
                        Path('aliexpress') / Path('orders')).resolve(),
            "ITEMS":  (Path(settings.SCRAPER_CACHE_BASE) / 
                       Path('aliexpress') / Path('items')).resolve(),
            }

        for key in self.cache:  # pylint: disable=consider-using-dict-items
            self.log.debug("Cache folder %s: %s", key, self.cache[key])
            try:
                os.makedirs(self.cache[key])
            except FileExistsError:
                pass

        self.snapshot_template = str(self.cache['ITEMS'] /
                                      Path("snapshot-{order_id}-{item_id}.pdf"))
        self.thumb_template = str(self.cache['ITEMS'] /
                                  Path("thumb-{order_id}-{item_id}.png"))
        self.cache_file_template = str(self.cache['ORDERS'] /
                                       Path("order-{order_id}.txt"))
        self.cache_tracking_file_template = str(self.cache['TRACKING'] /
                                                Path("tracking-{order_id}.txt"))

        self.order_list_cache_file = self.cache['BASE'] / Path('order-list.txt')
        self.pdf_temp_file = self.cache['BASE'] / Path('temporary-pdf.pdf')

    def scrape(self):
        '''
        Scrapes your AliExpress orders, logging you in using
        a automated browser if required.
        '''
        try:
            order_list_html = self.load_order_list_html()
            orders = self.lxml_parse_orderlist_html(order_list_html)
            self.get_individual_order_details(orders)
        except NoSuchWindowException:
            self._safe_quit()
            self.command.stdout.write(self.command.style.ERROR(
                'Login to Aliexpress was not successful. '
                'Please do not close the browser window.'))
            return
        finally:
            self._safe_quit()

    def _parse_order(self, order_inp, html):
        order = {}
        info_rows = html.xpath('//div[contains(@class, "info-row")]')
        for info_row in info_rows:
            text = "".join(info_row.itertext())
            if text.startswith("Payment"):
                order['payment_method'] = "".join(text.split(":")[1:]).strip()
        contact_info_div = html.xpath(
                '//div[contains(@class, "order-detail-info-item")]'
                '[not(contains(@class, "order-detail-order-info"))]'
                )[0]
        order['contact_info'] = list(contact_info_div.itertext())
        order['price_items'] = {}
        for price_item in html.xpath('//div[contains(@class, "order-price-item")]'):
            left = "".join(
                    price_item.xpath('.//span[contains(@class, "left-col")]')[0].itertext()
                    ).strip()
            order['price_items'][left] = "".join(
                    price_item.xpath('.//span[contains(@class, "right-col")]')[0].itertext()
                    ).strip()
        order['items'] = {}
        counter = 0
        for item in html.xpath('//div[contains(@class, "order-detail-item-content-wrap")]'):
            title_item = item.xpath('.//div[contains(@class, "item-title")]')[0]
            info = re.match(
                r'.+mailNoList=([A-Za-z0-9,]+)',
                title_item.xpath(
                    './/a'
                    )[0]
                )
            print(info.group(1))
            item_id = info.group(1)
            title = "".join(
                    title_item[0].itertext()
                    )
            sku_list = item.xpath('.//div[contains(@class, "item-sku-attr")]')
            if len(sku_list) == 0:
                sku = ""
            else:
                sku = "".join(sku_list[0].itertext())
            price_count = "".join(
                    item.xpath('.//div[contains(@class, "item-price")]')[0].itertext()
                    ).strip()
            (price, count) = price_count.split("x")
            # Remove space .. spacing
            title = re.sub(" +", " ", title)
            order['items'][item_id.strip()] = {
                    "title": title.strip(),
                    "sku": sku.strip(),
                    "price": price.strip(),
                    "count": int(count)
                    }
            counter += 1
        return order

    def visit_page(self, url):
        '''
        Instructs the browser to visit url. 

        If there is no browser instance, creates one.
        If login is required, does that.

            Returns:
                browser: (WebDriver) the browser instance
        '''
        self.browser = self.get_browser_instance()
        self.browser.get(url)
        if urlparse(self.browser.current_url).hostname == "login.aliexpress.com":
            # We were redirected to the login page
            self.browser_login(url)
        return self.browser

    def browser_scrape_order_details(self, order: Dict):
        '''
        Uses Selenium to visit, load and then save
        the HTML from the order details page of an individual order

        Will also save a copy of item thumbnails and a PDF copy
        of the item's snapshots, since this must be done live.

            Returns:
                order_html (HtmlElement): The HTML from this order['id'] details page
        '''
        url = self.ORDER_DETAIL_URL.format(order['id'])
        self.log.info("Visiting %s", url)
        c = self.visit_page(url)

        self.log.info("Waiting for page load")
        time.sleep(3)
        try:
            WebDriverWait(c, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//span[contains(@class, 'switch-icon')]")
                    ),"Timeout waiting for View orders button"
                )
            # Expand address and payment info
            for element in c.find_elements(
                    By.XPATH,
                    "//span[contains(@class, 'switch-icon')]"
                    ):
                element.click()
            time.sleep(1)
        except TimeoutException:
            pass

        c.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        # Save item IDs, thumbnails and PDf snapshots
        if not 'items' in order:
            order['items'] = {}
        for item_content in c.find_elements(
                By.XPATH,
                '//div[contains(@class, "order-detail-item-content-wrap")]'
                ):
            # Retrieve item ID from URL
            thumb = item_content.find_elements(
                By.XPATH,
                './/a[contains(@class, "order-detail-item-content-img")]'
                )[0]
            info = re.match(
                # https://www.aliexpress.com/item/32824370509.html
                r'.+item/([0-9]+)\.html',
                thumb.get_attribute("href")
                )
            item_id = info.group(1)
            self.log.debug("Curren item id is %s", item_id)
            if not item_id in order['items']:
                order['items'][item_id] = {}

            self.browser_save_item_thumbnail(order, thumb, item_id)
            # Get snapshot of order page from Ali's archives
            self.browser_save_item_sku_snapshot_to_pdf(order, thumb, item_id)

        self.log.info("Writing order details page to cache")
        with open(order['cache_file'], "w", encoding="utf-8") as ali_ordre:
            order_html = fromstring(c.page_source)
            ali_ordre.write(tostring(order_html).decode("utf-8"))

        return order_html

    def browser_save_item_thumbnail(self, order, thumb, item_id):
        snapshot_parent = thumb.find_element(
            By.XPATH,
            './/div[@class="order-detail-item-snapshot"]')
        # Hide the snapshot "camera" graphic that
        # overlays the thumbnail
        self.browser.execute_script(
            "arguments[0].setAttribute('style', 'display: none;')", 
            snapshot_parent
            )
        # Save copy of item thumbnail (without snapshot that
        # would appear if we screnshot the elemtns)
        thumb_data = thumb.screenshot_as_base64
        order['items'][item_id]['thumbnail'] = \
            self.thumb_template.format(
            order_id=order['id'],
            item_id=item_id
            )
        with open(order['items'][item_id]['thumbnail'], 'wb') as file:
            file.write(base64.b64decode(thumb_data))

    def browser_save_item_sku_snapshot_to_pdf(self, order, thumb, item_id, item_sku):
        '''
        Uses Selenium to save the AliExpress snapshot of the 
        current item id+item sku to PDF.
        '''
        order_details_page_handle = self.browser.current_window_handle
        self.log.debug("Order details page handle is %s", order_details_page_handle)
        snapshot = thumb.find_element(
            By.XPATH,
            './/div[contains(@class, "order-detail-item-snapshot")]//*[local-name()="svg"]'
            )
        snapshot.click()
        time.sleep(1)
        self.log.debug("Window handles: %s" , self.browser.window_handles)
        for handle in self.browser.window_handles:
            self.log.debug("Looking for snapshot tab of %s, current handle: %s", item_id, handle)
            if handle == order_details_page_handle:
                self.log.debug("Found order details page, skipping: %s", handle)
                continue
            self.browser.switch_to.window(handle)
            if "snapshot" in self.browser.current_url:
                if os.access(self.pdf_temp_file, os.R_OK):
                    os.remove(self.pdf_temp_file)
                self.log.debug("Found snapshot tab")
                self.log.debug("Trying to print to PDF")
                self.browser.execute_script('window.print();')
                    # Do some read- and size change tests
                    # to try to detect when printing is complete
                while not os.access(self.pdf_temp_file, os.R_OK):
                    self.log.debug("PDF file does not exist yet")
                    time.sleep(1)
                pdf_size_stable = False
                while not pdf_size_stable:
                    sz1 = os.stat(self.pdf_temp_file).st_size
                    time.sleep(2)
                    sz2 = os.stat(self.pdf_temp_file).st_size
                    time.sleep(2)
                    sz3 = os.stat(self.pdf_temp_file).st_size
                    pdf_size_stable = (sz1 == sz2 == sz3) and sz1+sz2+sz3 > 0
                    self.log.debug(
                        "Watching for stable file size larger than 0 bytes: %s %s %s",
                          sz1, sz2, sz3)
                    # We assume file has stabilized/print is complete
                order['items'][item_id]['snapshot'] = \
                    self.snapshot_template.format(
                    order_id=order['id'],
                    item_id=item_id
                    )
                try:
                    os.rename(self.pdf_temp_file, order['items'][item_id]['snapshot'])
                except FileExistsError:
                    self.log.info(
                        "Not overriding existing file: %s", 
                        order['items'][item_id]['snapshot']
                        )
            else:
                self.log.debug("Found random page, closing: %s", handle)
            self.browser.close()
        self.log.debug("Switching to order details page")
        self.browser.switch_to.window(order_details_page_handle)

    def get_individual_order_details(self, orders):
        '''
        ...
        '''
        if len(settings.SCRAPER_ALI_ORDERS):
            self.log.info("Scraping only order IDs from SCRAPER_ALI_ORDERS: %s", settings.SCRAPER_ALI_ORDERS)
        else:
            self.log.info("Scraping all order IDs")
        for order in orders:
            if len(settings.SCRAPER_ALI_ORDERS):
                if order['id'] not in settings.SCRAPER_ALI_ORDERS:
                    continue
            
            self.log.info("#"*30)
            self.log.info("Scraping order ID %s", order['id'])
            order_html: HtmlElement = HtmlElement()  # type: ignore
            tracking_html: HtmlElement = HtmlElement()  # type: ignore

            order['cache_file'] = self.cache_file_template.format(order_id=order['id'])
            order['tracking_cache_file'] = \
                self.cache_tracking_file_template.format(order_id=order['id'])

            if self.try_file and os.access(order['cache_file'], os.R_OK):
                with open(order['cache_file'], "r", encoding="utf-8") as ali_ordre:
                    self.log.debug("Loading individual order data from cache: %s", order['cache_file'])
                    order_html = fromstring(ali_ordre.read())
            else:
                order_html = self.browser_scrape_order_details(order)
            if self.try_file and os.access(order['tracking_cache_file'], os.R_OK):
                with open(order['tracking_cache_file'], "r", encoding="utf-8") as ali_ordre:
                    self.log.debug("Loading individual order tracking data cache: %s", order['tracking_cache_file'])
                    tracking_html = fromstring(ali_ordre.read())
            else:
                tracking_html = self.browser_scrape_tracking_page_html(order)

            order_data = self._parse_order(order, order_html)
            order.update(order_data)
            tracking = self._parse_tracking(order, tracking_html)
            order.update(tracking)
            print(json.dumps(order, indent=4, cls=DjangoJSONEncoder))

    def _parse_tracking(self, order: Dict, html: HtmlElement) -> Dict[str, Any]:
        tracking = {}
        if len(html.xpath('.//div[@class="tracking-module"]')) == 0:
            self.log.info("Order #%s has no tracking", order['id'])
            return {}
        info = re.match(
                r'.+mailNoList=([A-Za-z0-9,]+)',
                html.xpath(
                    '//a[contains(@href, "global.cainiao.com/detail.htm")]/@href'
                    )[0]
                )
        if info:
            tracking['numbers'] = info.group(1).split(',')
        service_upgraded = html.xpath('.//div[@class="service-upgraded"]')
        tracking['upgrade'] = None
        if len(service_upgraded):
            tracking['upgrade'] = service_upgraded[0].xpath(
                    './/div[@class="service-item-flex"]/span/text()'
                    )[0]
        tracking['shipper'] = html.xpath('//span[contains(@class, "title-eclp")]/text()')[0]
        tracking['status'] = html.xpath('//div[contains(@class, "status-title-text")]/text()')[0]
        addr = []
        for p_element in html.xpath('//div[contains(@class, "address-detail")]/p'):
            # Join and remove double spaces
            addr.append(" ".join("".join(p_element.itertext()).split()))
        tracking['addr'] = addr
        tracking['shipping'] = []
        for step in html.xpath('//ul[contains(@class, "ship-steps")]/li'):
            ship_time = step.xpath('.//p[contains(@class, "time")]')[0].text
            timezone = step.xpath('.//p[contains(@class, "timezone")]')[0].text
            try:
                head = step.xpath('.//p[contains(@class, "head")]')[0].text
            except IndexError:
                head = ""
            text = ("".join(step.xpath('.//p[contains(@class, "text")]')[0].itertext()))
            tracking['shipping'].append(
                    {
                        "time": ship_time,
                        "timezone": timezone,
                        "head": head,
                        "text": text
                        }) # type: ignore
        return tracking

    def lxml_parse_orderlist_html(self, order_list_html):
        '''
        Uses LXML to extract useful info from the HTML of the order list page

            Returns:
                orders (List[Dict]): List or order Dicts
        '''
        root = fromstring(order_list_html)
        order_items = root.xpath('//div[@class="order-item"]')
        orders = []
        for order in order_items:
            (order_status,) = order.xpath('.//span[@class="order-item-header-status-text"]')
            order_status = order_status.text.lower()
            right_info = order.xpath('.//div[@class="order-item-header-right-info"]/div')
            order_date = None
            order_id = None
            for div in right_info:
                info = re.match(
                        r'^Order (?:date: (?P<order_date>.+)|ID: (?P<order_id>\d+))',
                        div.text)
                if info:
                    if info.group('order_date'):
                        order_date = datetime.strptime(info.group('order_date'), '%b %d, %Y')
                    else:
                        order_id = info.group('order_id')
            if not all([order_date, order_id]):
                self.log.error("Unexpected data from order, failed to parse "
                        "order_id %s or order_date (%s)", order_id, order_date)
            (order_total,) = order.xpath('.//span[@class="order-item-content-opt-price-total"]')
            info = re.match(r'.+\$(?P<dollas>\d+\.\d+)', order_total.text)
            if info:
                order_total = float(info.group("dollas"))
            else:
                order_total = float("0.00")
            (order_store_id,) = order.xpath('.//span[@class="order-item-store-name"]/a')
            info = re.match(r'.+/store/(?P<order_store_id>\d+)', order_store_id.get('href'))
            order_store_id = info.group("order_store_id") if info else "0"
            (order_store_name,) = order.xpath('.//span[@class="order-item-store-name"]/a/span')
            order_store_name = order_store_name.text
            orders.append({
                    "id": order_id,
                    "status": order_status,
                    "date": order_date,
                    "total": order_total,
                    "store_id": order_store_id,
                    "store_name": order_store_name,
                })
        return orders

    def browser_scrape_tracking_page_html(self, order: Dict):
        '''
        Uses Selenium to visit, load and then save
        the HTML from the tracking page of an individual order

            Returns:
                tracking_html (HtmlElement): The HTML from this order['id'] tracking page
        '''
        self.visit_page(self.ORDER_TRACKING_URL.format(order['id']))
        time.sleep(1)
        self.browser.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        self.log.debug("Waiting 10 seconds for tracking page load")
        time.sleep(10)
        with open(order['tracking_cache_file'], "w", encoding="utf-8") as ali_ordre:
            tracking_html = fromstring(self.browser.page_source)
            ali_ordre.write(tostring(tracking_html).decode("utf-8"))
        return tracking_html

    def browser_scrape_order_list_html(self):
        '''
        Uses Selenium to visit, load, save and then
        return the HTML from the order list page

            Returns:
                order_list_html (str): The HTML from the order list page
        '''
        brws = self.visit_page(self.ORDER_URL)
        wait10 = WebDriverWait(brws, 10)
        # Find and click the tab for completed orders
        try:
            wait10.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//div[@class='comet-tabs-nav-item']"
                            "[contains(text(), 'Completed')]")
                        )
                    ).click()
        except ElementClickInterceptedException:
            # Apparently så var ikke sjekken over atomisk, så
            # vi venter litt til før vi klikker
            time.sleep(5)
            wait10.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[@class='comet-tabs-nav-item']"
                        "[contains(text(), 'Completed')]")
                    )
                ).click()

        # Wait until the tab for completed orders are complete
        wait10.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            ("//div[contains(@class, 'comet-tabs-nav-item') and "
                            "contains(@class, 'comet-tabs-nav-item-active')]"
                            "[contains(text(), 'Completed')]")))
                        )
        time.sleep(5)
        self.log.debug("Loading order page")
        while True:
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(3)
            try:
                element = wait10.until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//button[contains(@class, 'comet-btn')]"
                            "/span[contains(text(), 'View orders')]"
                            "/parent::button")
                        ),"Timeout waiting for View orders button"
                    )
                element.click()
            except StaleElementReferenceException:
                brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                time.sleep(3)
                continue
            except TimeoutException:
                break
        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        self.log.info("All completed orders loaded (hopefully)")
        with open(
                self.order_list_cache_file,
                "w",
                encoding="utf-8") as ali:
            html = fromstring(brws.page_source)
            ali.write(tostring(html).decode("utf-8"))
        return brws.page_source

    def indent(self):
        '''
        Uses Linux commands to create indented versions of
        all cached HTML files in cache["BASE"]
        
        Errors out on Windows.
        '''
        if os.name == "nt":
            self.log.error("Indentation only works on Linux")
            return
        cache = self.cache["BASE"].resolve()
        for path in cache.glob('*.txt'):
            path = path.resolve()
            in_file = path
            out_file = path.with_name(path.stem + ".xml")
            if os.access(out_file, os.R_OK):
                self.log.debug("File exists, skipping: %s", out_file)
                continue
            command = (f"sed 's/esi:include/include/g' '{in_file}' "
                    f"| xmllint --format - > '{out_file}'")
            subprocess.call(command, shell=True)

    def get_browser_instance(self):
        '''
        Initializing and configures a browser (Firefox)
        using Selenium.
        
        Returns a exsisting object if avaliable.

            Returns:
                browser (WebDriver): the configured and initialized browser
        '''
        if not hasattr(self, 'browser'):
            service = FirefoxService(executable_path=FirefoxDriverManager().install())
            self.log.debug("Initializing browser")
            options = Options()

            # Configure printing
            options.set_preference('print.always_print_silent', True)
            options.set_preference('print_printer', settings.SCRAPER_PDF_PRINTER)
            self.log.debug("Printer set to %s", settings.SCRAPER_PDF_PRINTER)
            printer_name = settings.SCRAPER_PDF_PRINTER.replace(" ","_")
            options.set_preference(f'print.printer_{ printer_name }.print_to_file', True)
            options.set_preference(
                f'print.printer_{ printer_name }.print_to_filename', str(self.pdf_temp_file))
            options.set_preference(
                f'print.printer_{ printer_name }.show_print_progress', True)

            self.browser = webdriver.Firefox(options=options, service=service)

            self.username = input("Enter Aliexpress username: ") \
                    if not settings.SCRAPER_ALI_USERNAME else settings.SCRAPER_ALI_USERNAME
            self.password = getpass("Enter Aliexpress password: ") \
                    if not settings.SCRAPER_ALI_PASSWORD else settings.SCRAPER_ALI_PASSWORD
            self.log.debug("Returning browser")
        return self.browser

    def browser_login(self, url):
        '''
        Uses Selenium to log in AliExpress.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required. 
        '''
        url = re.escape(url)
        self.log.info("We need to log in to Aliexpress")
        c = self.get_browser_instance() #  pylint: disable=invalid-name
        wait = WebDriverWait(c, 10)
        try:
            username = wait.until(
                    EC.presence_of_element_located((By.ID, "fm-login-id"))
                    )
            password = wait.until(
                    EC.presence_of_element_located((By.ID, "fm-login-password"))
                    )
            username.send_keys(self.username)
            password.send_keys(self.password)
            wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@type='submit'][not(@disabled)]")
                        )
                    ).click()
            order_page = False
            try:
                self.log.debug(
                    "Current url: %s correct url: %s", 
                    c.current_url,
                    c.current_url==url)
                WebDriverWait(c, 5).until(EC.url_matches(url))
                order_page = True
            except TimeoutException:
                pass
            if not order_page:
                c.execute_script(
                    "alert('Please complete login (CAPTCHA etc.). You have two minutes.');"
                    )
                self.log.warning('Please complete log in to Aliexpress in the browser window..')
                WebDriverWait(c, 30).until_not(
                        EC.alert_is_present(),
                        "Please close altert an continue login!"
                        )
                self.log.info("Waiting up to 120 seconds for %s", url)
                WebDriverWait(c, 120).until(EC.url_matches(url))
        except TimeoutException:
            try:
                c.switch_to.alert.accept()
            except NoAlertPresentException:
                pass
            self._safe_quit()
            # pylint: disable=raise-missing-from
            raise CommandError('Login to Aliexpress was not successful.')

    def _safe_quit(self):
        '''
        Safely closed the browser instance. (without exceptions)
        '''
        self.log.info("Safely closing browser")
        try:
            if hasattr(self, 'chrome'):
                self.browser.quit()
        except WebDriverException:
            pass

    def load_order_list_html(self):
        '''
        Returns the order list html, eithter from disk
        cache or using Selenium to visit the url.

            Returns:
                order_list_html (str): The HTML from the order list page
        '''
        if self.try_file:
            if os.access(self.order_list_cache_file, os.R_OK):
                self.log.info("Loading order list from cache: %s", self.order_list_cache_file)
                with open(
                        self.order_list_cache_file,
                        "r",
                        encoding="utf-8") as ali:
                    return ali.read()
            else:
                self.log.info("Tried to use order list cache, but found none")
        else:
            self.log.info("Not using order list cache")
            if not hasattr(self, 'order_list_html'):
                self.log.debug("Order list html not cached, retrieving")
                return self.browser_scrape_order_list_html()
