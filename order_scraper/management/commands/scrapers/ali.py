import re
import os
import time
from urllib.parse import urlparse
from typing import List
from getpass import getpass
from datetime import datetime

# This is used in a Django command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import \
        TimeoutException, \
        NoSuchWindowException, \
        NoAlertPresentException, \
        StaleElementReferenceException, \
        WebDriverException
from selenium.webdriver.support import expected_conditions as EC

from lxml.html.soupparser import fromstring
from lxml.etree import tostring

# https://docs.djangoproject.com/en/3.2/ref/django-admin/

class AliScraper():  # pylint: disable=too-few-public-methods
    ORDER_URL: str = 'https://www.aliexpress.com/p/order/index.html'
    chrome: webdriver.Chrome
    previous_orders: List
    order_list_html: str
    username: str
    password: str

    def __init__(self, command: BaseCommand, try_file: bool = False):
        self.command = command
        if try_file:
            if os.access("cache-scraper-aliexpress.txt", os.R_OK):
                with open("cache-scraper-aliexpress.txt", "r", encoding="utf-8") as ali:
                    self.order_list_html = ali.read()
            else:
                self._notice("Tried to use cache, but found none")
        if not hasattr(self, 'order_list_html'):
            try:
                self.order_list_html = self._get_order_list_html()
            except (TypeError, NoSuchWindowException):
                self._safe_quit()
                self.command.stdout.write(self.command.style.ERROR(
                    'Login to Aliexpress was not successful. '
                    'Please do not close the browser window.'))
                return
            finally:
                self._safe_quit()
        self._parse_orderlist_html()

    def _get_chrome(self):
        if not hasattr(self, 'chrome'):
            options = Options()
            self.chrome = webdriver.Chrome(chrome_options=options)
            self.username = input("Enter Aliexpress username: ") \
                    if not settings.SCRAPER_ALI_USERNAME else settings.SCRAPER_ALI_USERNAME
            self.password = getpass("Enter Aliexpress password: ") \
                    if not settings.SCRAPER_ALI_PASSWORD else settings.SCRAPER_ALI_PASSWORD
        return self.chrome

    def _parse_orderlist_html(self):
        root = fromstring(self.order_list_html)
        order_items = root.xpath('//div[@class="order-item"]')
        orders = []
        for order in order_items:
            print("#"*30)
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
                        print(f"#{order_id}")
            if not all([order_date, order_id]):
                self._error(f"Unexpected data from order, failed to parse "
                        f"order_id {order_id} or order_date ({order_date})")
            (order_total,) = order.xpath('.//span[@class="order-item-content-opt-price-total"]')
            info = re.match(r'.+\$(?P<dollas>\d+\.\d+)', order_total.text)
            if info:
                order_total = float(info.group("dollas"))
            else:
                order_total = float("0.00")
            orders.append({
                    "order_id": order_id,
                    "order_status": order_status,
                    "order_date": order_date,
                    "order_total": order_total
                })
        print("#"*30)
        total_spent = sum(float(x['order_total']) for x in orders if x['order_status'] != 'cancelled' and x['order_date'] < datetime(2020, 3, 12))
        print(f"Aliexpress total spent: US ${total_spent:.2f}")

    def _safe_quit(self):
        try:
            self.chrome.quit()
        except WebDriverException:
            pass

    def _error(self, msg):
        self.command.stdout.write(self.command.style.ERROR(msg))

    def _success(self, msg):
        self.command.stdout.write(self.command.style.SUCCESS(msg))

    def _notice(self, msg):
        self.command.stdout.write(self.command.style.NOTICE(msg))

    def _get_order_list_html(self):
        c = self._get_chrome() #  pylint: disable=invalid-name
        c.get(self.ORDER_URL)
        check_login = urlparse(c.current_url)
        wait = WebDriverWait(c, 10)
        if check_login.hostname == "login.aliexpress.com":
            # We were redirected to the login page
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
                    WebDriverWait(c, 5).until(EC.url_matches(self.ORDER_URL))
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
                    WebDriverWait(c, 120).until(EC.url_matches(self.ORDER_URL))
            except TimeoutException:
                try:
                    c.switch_to.alert.accept()
                except NoAlertPresentException:
                    pass
                self._safe_quit()
                # pylint: disable=raise-missing-from
                raise CommandError('Login to Aliexpress was not successful.')

        # Find and click the tab for completed orders
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
        with open("cache-scraper-aliexpress.txt", "w", encoding="utf-8") as ali:
            html = fromstring(c.page_source)
            ali.write(tostring(html).decode("utf-8"))
        return c.page_source
