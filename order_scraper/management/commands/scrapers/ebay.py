import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from django.core.files import File

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from ....models.attachement import Attachement
from ....models.order import Order
from ....models.orderitem import OrderItem
from ....models.shop import Shop
from .base import BaseScraper, PagePart


class EbayScraper(BaseScraper):
    # Scrape comand and __init__
    def command_scrape(self):
        if False:
            pass
        else:
            # https://signin.ebay.com/ws/eBayISAPI.dll?SignIn&ru=https%3A%2F%2Fwww.ebay.com%2F
            # input id userid
            # button id signin-continue-btn

            # input id pass
            # button id sgnBt
            self.browser_visit_page(url, False)

            # if div id captcha_loading:
            # uiser interaction

            # https://www.ebay.com/mye/myebay/purchase
            # mobile? https://www.ebay.com/mye/myebay/purchase?pg=purchase

            # mobile a class m-pagination-simple-next [aria-disabled="true"]

            # UA Mozilla/5.0 (Android 13; Mobile; rv:68.0) Gecko/68.0 Firefox/112.0
            # url stats with https://signin.ebay.com
            https://www.ebay.com/mye/myebay -> login
            https://www.ebay.com/mye/myebay/purchase?pg=purchase
            # div.m-mweb-item-container
                a.m-mweb-item-link
                div.m-image -> img -> thumbnail
            
                div.item-details
                    div.item-banner-text -> status refunded/shippet etc
                    h2.item-title
                    div.item-variation (optional, SKU)
                    div.item-info
                        span.info-displayprice -> span BOLD, clipped (forskjell???)
                        span.info-logisticscost -> span or span.clipped (more info?)
                        span.info-orderdate
            
            # span class filter -> span text "Last 60 Days" -> click
            data-url: data-url="/module_provider?filter=year_filter:LAST_YEAR&page=1&modules=ALL_TRANSACTIONS&moduleId=122164" ?
https://www.ebay.com/mye/myebay/v2/purchase?filter=year_filter%3ALAST_YEAR&page=1&moduleId=122164&pg=purchase&mp=purchase-module-v2&type=v2
            https://www.ebay.com/mye/myebay/v2/purchase?filter=year_filter%3ATWO_YEARS_AGO&page=1&moduleId=122164&pg=purchase&mp=purchase-module-v2&type=v2

            <span class="m-container-message__content">No orders were found</span>
            self.browser_safe_quit()
        pass

    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options, __name__)
        self.setup_cache("ebay")
        self.setup_templates()

    def command_db_to_csv(self):
        pass

    def command_load_to_db(self):
        pass

    # LXML-heavy functions
    # ...

    # Selenium-heavy function
    def browser_detect_handle_interrupt(self, url):
        pass

    def browser_login(self, _):
        return False

    # Utility functions
    def setup_templates(self):
        # pylint: disable=invalid-name
        self.ORDERS_CSV = self.cache["BASE"] / "order_history.csv"
        self.ITEMS_CSV = self.cache["BASE"] / "products_history.csv"
        self.ITEM_URL_TEMPLATE = "https://www.adafruit.com/product/{item_id}"
        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/order.{ext}")
        )
        self.ORDER_ITEM_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/item-{item_id}.{ext}")
        )

    def part_to_filename(self, part: PagePart, **kwargs):
        template: str
        if part == PagePart.ORDER_DETAILS:
            template = self.ORDER_FILENAME_TEMPLATE
        elif part == PagePart.ORDER_ITEM:
            template = self.ORDER_ITEM_FILENAME_TEMPLATE
        return Path(template.format(**kwargs))
