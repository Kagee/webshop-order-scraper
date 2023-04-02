import re
from getpass import getpass
from typing import Dict, Final

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from .base import BaseScraper


class AmazonScraper(BaseScraper):
    TLD: str = "test"
    ORDER_LIST_PATH: Final[str] = '/css/order-history?ref_=nav_orders_first'
    ORDER_LIST_URL_DICT: Final[Dict[str, str]] = \
        { "de": f'https://www.amazon.de/-/en/gp{ORDER_LIST_PATH}',
          "com": f'https://www.amazon.com/gp{ORDER_LIST_PATH}',
          "co.uk": f'https://www.amazon.co.uk/gp{ORDER_LIST_PATH}',
        }
    ORDER_LIST_URL: str = f'https://www.amazon.test/-/en/gp{ORDER_LIST_PATH}'
    ORDER_DETAIL_URL_DICT: Final[Dict[str, str]] = \
        { "de":
         'https://www.amazon.de/gp/your-account/order-details?ie=UTF8&orderID={order_id}',
          "com":
          'https://www.amazon.com/gp/your-account/order-details?ie=UTF8&orderID={order_id}',
          "co.uk":
          'https://www.amazon.co.uk/gp/your-account/order-details?ie=UTF8&orderID={order_id}',
        }
    ORDER_DETAIL_URL: str = \
        'https://www.amazon.test/gp/your-account/order-details?ie=UTF8&orderID={order_id}'

    #ORDER_TRACKING_URL: Final[str] = 'https://track.aliexpress.com/logisticsdetail.htm?tradeId={}'


    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options)
        self.command = command

    def browser_login(self, url):
        '''
        Uses Selenium to log in AliExpress.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required.
        '''
        # We (optionally) ask for this here and not earlier, since we
        # may not need to go live
        self.username = input(f"Enter Amazon.{self.TLD} username: ") \
                if not settings.SCRAPER_AMZDE_USERNAME else settings.SCRAPER_AMZDE_USERNAME
        self.password = getpass(f"Enter Amazon.{self.TLD} password: ") \
                if not settings.SCRAPER_AMZDE_PASSWORD else settings.SCRAPER_AMZDE_PASSWORD
        url_re_escaped = re.escape(url)
        order_list_url_re_espaced = re.escape(self.ORDER_LIST_URL)

        self.log.info(self.command.style.NOTICE("We need to log in to Aliexpress"))
        c = self.browser_get_instance() #  pylint: disable=invalid-name
        # We go to the order list, else ... maybe russian?
        c.get(self.ORDER_LIST_URL)

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
            order_list_page = False
            try:
                self.log.debug(
                    "Current url: %s correct url: %s",
                    c.current_url,
                    c.current_url==url_re_escaped)
                WebDriverWait(c, 5).until(EC.url_matches(order_list_url_re_espaced))
                order_list_page = True
            except TimeoutException:
                pass
            if not order_list_page:
                c.execute_script(
                    "alert('Please complete login (CAPTCHA etc.). You have two minutes.');"
                    )
                self.log.warning('Please complete log in to Aliexpress in the browser window..')
                WebDriverWait(c, 30).until_not(
                        EC.alert_is_present(),
                        "Please close altert an continue login!"
                        )
                self.log.info("Waiting up to 120 seconds for %s", order_list_url_re_espaced)
                WebDriverWait(c, 120).until(EC.url_matches(order_list_url_re_espaced))
        except TimeoutException:
            try:
                c.switch_to.alert.accept()
            except NoAlertPresentException:
                pass
            self.browser_safe_quit()
            # pylint: disable=raise-missing-from
            raise CommandError('Login to Aliexpress was not successful.')
        c.get(url)
        self.log.info("Waiting up to 120 seconds for %s", url_re_escaped)
        WebDriverWait(c, 120).until(EC.url_matches(url_re_escaped))
