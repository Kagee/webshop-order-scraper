import re
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
# https://www.browserstack.com/guide/get-current-url-in-selenium-and-python
from lxml.html.soupparser import fromstring

from django.core.management.base import BaseCommand, CommandError

class AliScraper():
    def __init__(self, command: BaseCommand):
        self.command = command

    def get_orders(self):
        # https://www.aliexpress.com/p/order/index.html
        self.command.stdout.write(self.command.style.SUCCESS('Scarpe complete'))
        return
        options = Options()
        #options.add_argument('--headless')
        #options.add_argument('--disable-gpu')
        chrome = webdriver.Chrome(chrome_options=options)
        chrome.get('https://www.aliexpress.com/p/order/index.html')
        check_login = urlparse(chrome.current_url)
        if check_login.hostname == "login.aliexpress.com":
            wait = WebDriverWait(chrome, 10)
            try:
                password = wait.until(
                                    EC.presence_of_element_located((By.ID, "fm-login-password"))
                                        )
            except TimeoutException:
                chrome.quit()
                raise CommandError('Login to Aliexpress was not successful.')
    
            chrome.find_element(
                        By.XPATH,
                        "//div[@class='comet-tabs-nav-item'][contains(text(), 'Completed')]"
                        ).click()
            _completed_view  = wait.until(
                                    EC.presence_of_element_located(
                                        (
                                            By.XPATH,
                                            ("//div[contains(@class, 'comet-tabs-nav-item') and "
                                            "contains(@class, 'comet-tabs-nav-item-active')]"
                                            "[contains(text(), 'Completed')]")))
                                        )
            chrome.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            html = chrome.page_source
            chrome.close()
            with open("ali1.txt", "w", encoding="utf-8") as ali:
                ali.write(html)

    def index(_request):
        # https://www.aliexpress.com/p/order/index.html
        options = Options()
        #options.add_argument('--headless')
        #options.add_argument('--disable-gpu')
        chrome = webdriver.Chrome(chrome_options=options)
        chrome.get('https://www.aliexpress.com/p/order/index.html')
        check_login = urlparse(chrome.current_url)
        status = "Unknown"
        # cookies https://stackoverflow.com/questions/
        # 15058462/how-to-save-and-load-cookies-using-python-selenium-webdriver
        if check_login.hostname == "login.aliexpress.com":
            status = "Not logged in"
            wait = WebDriverWait(chrome, 10)
            try:
                username = wait.until(
                                    EC.presence_of_element_located((By.ID, "fm-login-id"))
                                        )
    
                password = wait.until(
                                    EC.presence_of_element_located((By.ID, "fm-login-password"))
                                        )
                username.send_keys("hildenae@gmail.com")
                password.send_keys("tCd77PT3vxw33wUSyS71")
                wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[@type='submit'][not(@disabled)]")
                    )).click()
                wait.until(EC.url_matches("www.aliexpress.com/p/order/index.html"))
                status = "Logged in"
            except TimeoutException:
                chrome.quit()
    
            chrome.find_element(
                        By.XPATH,
                        "//div[@class='comet-tabs-nav-item'][contains(text(), 'Completed')]"
                        ).click()
            _completed_view  = wait.until(
                                    EC.presence_of_element_located(
                                        (
                                            By.XPATH,
                                            ("//div[contains(@class, 'comet-tabs-nav-item') and "
                                            "contains(@class, 'comet-tabs-nav-item-active')]"
                                            "[contains(text(), 'Completed')]")))
                                        )
            chrome.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            html = chrome.page_source
            chrome.close()
            with open("ali1.txt", "w", encoding="utf-8") as ali:
                ali.write(html)
    
    def test404(_request):
        html = ""
        with open("ali1.txt", "r", encoding="utf-8") as ali:
            html = ali.read()
        root = fromstring(html)
        #_orders = root.xpath('//div[@class="order-item"]')
        orders = root.xpath("//div[contains(text(), 'Order ID:')]")
        for order in orders:
            x = re.findall(r'\d*', order.text)
            if x:
                print(f"Match in '{order.text}' ('{order.text.encode('utf-8').hex()}')({type(order.text)}): {x}")
                y = [y.encode('utf-8').hex() for y in x]
                print(f"Match in '{order.text}' ({type(order.text)}): {y}")
            else:
              print(f"No match in {order.text}")
    
    #def test404(_request):
    #    raise Http404("Question does not exist")
