import re
import os
import time
from urllib.parse import urlparse
from typing import List, Final, Dict, Any
from getpass import getpass
from datetime import datetime
from pathlib import Path
import subprocess
import json
import base64
from urllib.parse import urlparse

from webdriver_manager.firefox import GeckoDriverManager as FirefoxDriverManager # type: ignore
from selenium.webdriver.firefox.service import Service as FirefoxService

# This is used in a Django command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import \
        TimeoutException, \
        NoSuchWindowException, \
        NoAlertPresentException, \
        StaleElementReferenceException, \
        WebDriverException, \
        ElementClickInterceptedException
from selenium.webdriver.support import expected_conditions as EC

from lxml.html.soupparser import fromstring
from lxml.etree import tostring
from lxml.html import HtmlElement

class AliScraper():
    ORDER_URL: Final[str] = 'https://www.aliexpress.com/p/order/index.html'
    ORDER_DETAIL_URL: Final[str] = 'https://www.aliexpress.com/p/order/detail.html?orderId={}'
    ORDER_TRACKING_URL: Final[str] = 'https://track.aliexpress.com/logisticsdetail.htm?tradeId={}'
    browser: webdriver.Firefox
    previous_orders: List
    order_list_html: str
    orders: list
    username: str
    password: str
    try_file: bool
    cache: Dict[str, Path]
    pdf_temp_file: Path

    def __init__(self, command: BaseCommand, try_file: bool = False):
        self.command = command
        self.try_file = try_file
        self.cache = {
            "BASE": (Path(settings.SCRAPER_CACHE_BASE) / Path('aliexpress')).resolve(),
            "TRACKING":  (Path(settings.SCRAPER_CACHE_BASE) / Path('aliexpress') / Path('tracking')).resolve(),
            "ORDERS":  (Path(settings.SCRAPER_CACHE_BASE) / Path('aliexpress') / Path('orders')).resolve(),
            "ITEMS":  (Path(settings.SCRAPER_CACHE_BASE) / Path('aliexpress') / Path('items')).resolve(),
            }
        try:
            for key in self.cache:
                os.makedirs(self.cache[key])
        except FileExistsError:
            pass
        self.snapshot_template = str(self.cache['ITEMS'] / Path("snapshot-{order_id}-{item_id}.pdf"))
        self.thumb_template = str(self.cache['ITEMS'] / Path("thumb-{order_id}-{item_id}.png"))
        self.cache_file_template = str(self.cache['ORDERS'] / Path("order-{order_id}.txt"))
        self.cache_tracking_file_template = str(self.cache['TRACKING'] / Path("tracking-{order_id}.txt"))

        self.order_list_cache = self.cache['BASE'] / Path('order-list.txt')
        self.pdf_temp_file = self.cache['BASE'] / Path('temporary-pdf.pdf')

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

    def scrape(self):
        if self.try_file:
            if os.access(self.order_list_cache, os.R_OK):
                with open(
                        self.order_list_cache,
                        "r",
                        encoding="utf-8") as ali:
                    self.order_list_html = ali.read()
            else:
                self._notice("Tried to use cache, but found none")
        try:
            if not hasattr(self, 'order_list_html'):
                self.order_list_html = self._get_order_list_html()
            self.orders = self._parse_orderlist_html()
            self._get_order_details()
        except NoSuchWindowException:
            self._safe_quit()
            self.command.stdout.write(self.command.style.ERROR(
                'Login to Aliexpress was not successful. '
                'Please do not close the browser window.'))
            return
        finally:
            self._safe_quit()

    def _scrape_order_details(self, order):
        url = self.ORDER_DETAIL_URL.format(order['id'])
        self._notice(f"Visiting {url}")
        c = self._get_browser() #  pylint: disable=invalid-name
        c.get(url)
        if urlparse(c.current_url).hostname == "login.aliexpress.com":
            # We were redirected to the login page
            self._login(url)

        self._notice("Waiting for page load")
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
            thumb = item_content.find_elements(By.XPATH, './/a[contains(@class, "order-detail-item-content-img")]')[0]
            info = re.match(
                # https://www.aliexpress.com/item/32824370509.html
                r'.+item/([0-9]+)\.html',
                thumb.get_attribute("href")
                )
            item_id = info.group(1)
            self._out(f"Curren item id is {item_id}")
            if not item_id in order['items']:
                order['items'][item_id] = {}
            # Get snapshot of order page from Ali's archives
            order_details_page_handle = c.current_window_handle
            self._out(f"Order details page handle is {order_details_page_handle}")
            snapshot = thumb.find_element(By.XPATH, './/div[contains(@class, "order-detail-item-snapshot")]//*[local-name()="svg"]')
            snapshot.click()
            time.sleep(1)
            self._out(f"Window handles: {c.window_handles}")
            for handle in c.window_handles:
                self._out(f"Looking for snapshot tab of {item_id}, current handle: {handle}")
                if handle == order_details_page_handle:
                    self._out(f"Found orde details, skipping: {handle}")
                    continue
                c.switch_to.window(handle)
                if "snapshot" in c.current_url:
                    if os.access(self.pdf_temp_file, os.R_OK):
                        os.remove(self.pdf_temp_file)
                    self._notice("Found snapshot tab")
                    self._out("Trying to print")
                    c.execute_script('window.print();')
                    # Do some read- and size change tests
                    # to try to detect when printing is complete
                    while not os.access(self.pdf_temp_file, os.R_OK):
                        self._out("PDF file does not exist yet")
                        time.sleep(1)   
                    pdf_size_stable = False
                    while not pdf_size_stable:
                        sz1 = os.stat(self.pdf_temp_file).st_size
                        time.sleep(2)
                        sz2 = os.stat(self.pdf_temp_file).st_size
                        time.sleep(2)
                        sz3 = os.stat(self.pdf_temp_file).st_size
                        pdf_size_stable = (sz1 == sz2 == sz3) and sz1+sz2+sz3 > 0
                        self._out(f"Watching for stabale file side >0: {sz1} {sz2} {sz3}")
                    # We assume file has stabilized/print is complete
                    order['items'][item_id]['snapshot'] = self.snapshot_template.format(order_id=order['id'], item_id=item_id)
                    try:
                        os.rename(self.pdf_temp_file, order['items'][item_id]['snapshot'])
                    except FileExistsError:
                        self._notice(f"Not overriding existing file: {order['items'][item_id]['snapshot']}")
                else:
                    self._out(f"Found random page, closnig: {handle}")
                c.close()
            self._out("Switching to order details page")
            c.switch_to.window(order_details_page_handle)
            s = thumb.find_element(By.XPATH, './/div[@class="order-detail-item-snapshot"]')
            c.execute_script("arguments[0].setAttribute('style', 'display: none;')", snapshot_parent);
            # Save copy of item thumbnail (without snapshot that would appear if we screnshot the elemtns)
            #thumb = item_content.find_elements(By.XPATH, './/a[contains(@class, "order-detail-item-content-img")]')[0]
            thumb_data = thumb.screenshot_as_base64
            order['items'][item_id]['thumbnail'] = self.thumb_template.format(order_id=order['id'], item_id=item_id)
            with open(order['items'][item_id]['thumbnail'], 'wb') as file:
                file.write(base64.b64decode(thumb_data))
            
            order_details_page_handle = c.current_window_handle
            self._out(f"Order details page handle is {order_details_page_handle}")
            snapshot = thumb.find_element(By.XPATH, './/div[contains(@class, "order-detail-item-snapshot")]//*[local-name()="svg"]')
            snapshot.click()
            time.sleep(1)
            self._out(f"Window handles: {c.window_handles}")
            for handle in c.window_handles:
                self._out(f"Looking for snapshot tab of {item_id}, current handle: {handle}")
                if handle == order_details_page_handle:
                    self._out(f"Found orde details, skipping: {handle}")
                    continue
                c.switch_to.window(handle)
                if "snapshot" in c.current_url:
                    if os.access(self.pdf_temp_file, os.R_OK):
                        os.remove(self.pdf_temp_file)
                    self._notice("Found snapshot tab")
                    self._out("Trying to print")
                    c.execute_script('window.print();')
                    # Do some read- and size change tests
                    # to try to detect when printing is complete
                    while not os.access(self.pdf_temp_file, os.R_OK):
                        self._out("PDF file does not exist yet")
                        time.sleep(1)   
                    pdf_size_stable = False
                    while not pdf_size_stable:
                        sz1 = os.stat(self.pdf_temp_file).st_size
                        time.sleep(2)
                        sz2 = os.stat(self.pdf_temp_file).st_size
                        time.sleep(2)
                        sz3 = os.stat(self.pdf_temp_file).st_size
                        pdf_size_stable = (sz1 == sz2 == sz3) and sz1+sz2+sz3 > 0
                        self._out(f"Watching for stabale file side >0: {sz1} {sz2} {sz3}")
                    # We assume file has stabilized/print is complete
                    order['items'][item_id]['snapshot'] = self.snapshot_template.format(order_id=order['id'], item_id=item_id)
                    try:
                        os.rename(self.pdf_temp_file, order['items'][item_id]['snapshot'])
                    except FileExistsError:
                        self._notice(f"Not overriding existing file: {order['items'][item_id]['snapshot']}")
                else:
                    self._out(f"Found random page, closnig: {handle}")
                c.close()
            self._out("Switching to order details page")
            c.switch_to.window(order_details_page_handle)
        self._out("Writing order details page to cache")
        with open(order['cache_file'], "w", encoding="utf-8") as ali_ordre:
            order_html = fromstring(c.page_source)
            ali_ordre.write(tostring(order_html).decode("utf-8"))
        c.get(self.ORDER_TRACKING_URL.format(order['id']))
        time.sleep(1)
        c.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        self._notice("Waiting 10 seconds for tracking page load")
        time.sleep(10)
        with open(order['tracking_cache_file'], "w", encoding="utf-8") as ali_ordre:
            tracking_html = fromstring(c.page_source)
            ali_ordre.write(tostring(tracking_html).decode("utf-8"))
        return order_html, tracking_html


    def _get_order_details(self):
        for order in self.orders:
            if len(settings.SCRAPER_ALI_ORDERS):
                if order['id'] not in settings.SCRAPER_ALI_ORDERS:
                    continue
            order_html: HtmlElement = HtmlElement()  # type: ignore
            tracking_html: HtmlElement = HtmlElement()  # type: ignore
            self._out("#"*30)
            self._success(f"Order ID: {order['id']}")
            order['cache_file'] = self.cache_file_template.format(order_id=order['id'])
            order['tracking_cache_file'] = self.cache_tracking_file_template.format(order_id=order['id'])
            if self.try_file and os.access(order['cache_file'], os.R_OK):
                with open(order['cache_file'], "r", encoding="utf-8") as ali_ordre:
                    order_html = fromstring(ali_ordre.read())
                with open(order['tracking_cache_file'], "r", encoding="utf-8") as ali_ordre:
                    tracking_html = fromstring(ali_ordre.read())
            else:
                order_html, tracking_html = self._scrape_order_details(order)
            order_data = self._parse_order(order, order_html)
            order.update(order_data)
            tracking = self._parse_tracking(order, tracking_html)
            order.update(tracking)
            print(json.dumps(order, indent=4, cls=DjangoJSONEncoder))

    def _parse_tracking(self, order: Dict, html: HtmlElement) -> Dict[str, Any]:
        tracking = {}
        if len(html.xpath('.//div[@class="tracking-module"]')) == 0:
            self._notice(f"Order #{order['id']} has no tracking")
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


    def _get_browser(self):
        if not hasattr(self, 'browser'):
            service = FirefoxService(executable_path=FirefoxDriverManager().install())
            self._notice("Creating browser")
            options = Options()

            # Configure printing
            options.set_preference('print.always_print_silent', True)
            options.set_preference('print_printer', settings.SCRAPER_PDF_PRINTER)
            printer_name = settings.SCRAPER_PDF_PRINTER.replace(" ","_")
            options.set_preference(f'print.printer_{ printer_name }.print_to_file', True)
            options.set_preference(f'print.printer_{ printer_name }.print_to_filename', str(self.pdf_temp_file));
            options.set_preference(f'print.printer_{ printer_name }.show_print_progress', True);

            self.browser = webdriver.Firefox(options=options, service=service)

            self.username = input("Enter Aliexpress username: ") \
                    if not settings.SCRAPER_ALI_USERNAME else settings.SCRAPER_ALI_USERNAME
            self.password = getpass("Enter Aliexpress password: ") \
                    if not settings.SCRAPER_ALI_PASSWORD else settings.SCRAPER_ALI_PASSWORD
            self._notice("Returning browser")
        return self.browser

    def _login(self, url):
        url = re.escape(url)
        self._notice("We ned to log in")
        c = self._get_browser() #  pylint: disable=invalid-name
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
                self._notice(f"Current url: {c.current_url} correct url: {c.current_url==url}")
                WebDriverWait(c, 5).until(EC.url_matches(url))
                order_page = True
            except TimeoutException:
                pass
            if not order_page:
                c.execute_script(
                    "alert('Please complete login (CAPTCHA etc.). You have two minutes.');"
                    )
                self._notice('Please complete log in to Aliexpress in the browser window..')
                WebDriverWait(c, 30).until_not(
                        EC.alert_is_present(),
                        "Please close altert an continue login!"
                        )
                self._notice(f"Waiting up to 120 seconds for {url}")
                WebDriverWait(c, 120).until(EC.url_matches(url))
        except TimeoutException:
            try:
                c.switch_to.alert.accept()
            except NoAlertPresentException:
                pass
            self._safe_quit()
            # pylint: disable=raise-missing-from
            raise CommandError('Login to Aliexpress was not successful.')

    def _parse_orderlist_html(self):
        root = fromstring(self.order_list_html)
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
                self._error(f"Unexpected data from order, failed to parse "
                        f"order_id {order_id} or order_date ({order_date})")
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

    def _safe_quit(self):
        try:
            if hasattr(self, 'chrome'):
                self.browser.quit()
        except WebDriverException:
            pass

    def _out(self, msg):
        self.command.stdout.write(msg)

    def _error(self, msg):
        self.command.stdout.write(self.command.style.ERROR(msg))

    def _success(self, msg):
        self.command.stdout.write(self.command.style.SUCCESS(msg))

    def _notice(self, msg):
        self.command.stdout.write(self.command.style.NOTICE(msg))

    def _get_order_list_html(self):
        c = self._get_browser() #  pylint: disable=invalid-name
        c.get(self.ORDER_URL)
        check_login = urlparse(c.current_url)
        wait = WebDriverWait(c, 10)
        if check_login.hostname == "login.aliexpress.com":
            # We were redirected to the login page
            self._login(self.ORDER_URL)
        # Find and click the tab for completed orders
        try:
            wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//div[@class='comet-tabs-nav-item']"
                            "[contains(text(), 'Completed')]")
                        )
                    ).click()
        except ElementClickInterceptedException:
            # Apparently så var ikke sjekken over atomisk, så 
            # vi venter litt til før vi klikker
            wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[@class='comet-tabs-nav-item']"
                        "[contains(text(), 'Completed')]")
                    )
                ).click()
        # Wait until the tab for completed orders are complete
        WebDriverWait(c, 10).until(
                                EC.presence_of_element_located(
                                    (
                                        By.XPATH,
                                        ("//div[contains(@class, 'comet-tabs-nav-item') and "
                                        "contains(@class, 'comet-tabs-nav-item-active')]"
                                        "[contains(text(), 'Completed')]")))
                                    )
        time.sleep(5)
        self._notice("Loading order page")
        while True:
            c.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(3)
            try:
                element = wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//button[contains(@class, 'comet-btn')]"
                            "/span[contains(text(), 'View orders')]"
                            "/parent::button")
                        ),"Timeout waiting for View orders button"
                    )
                element.click()
            except StaleElementReferenceException:
                c.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                time.sleep(3)
                continue
            except TimeoutException:
                break
        c.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        self._notice("All completed orders loaded (hopefully)")
        with open(
                self.order_list_cache,
                "w",
                encoding="utf-8") as ali:
            html = fromstring(c.page_source)
            ali.write(tostring(html).decode("utf-8"))
        return c.page_source

    def indent(self):
        cache = Path(settings.SCRAPER_CACHE).resolve()
        for path in cache.glob('*aliexpress*.txt'):
            path = path.resolve()
            in_file = path
            out_file = path.with_name(path.stem + ".xml")
            if os.access(out_file, os.R_OK):
                self._success(f"File exists, skipping: {out_file}")
                continue
            command = (f"sed 's/esi:include/include/g' '{in_file}' "
                    f"| xmllint --format - > '{out_file}'")
            subprocess.call(command, shell=True)
