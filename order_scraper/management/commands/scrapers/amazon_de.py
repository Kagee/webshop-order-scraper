import datetime
import getpass
import logging
import random
import re
import time
from typing import Dict, Final


# This is used in a Django command
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


from .amazon import AmazonScraper

# Inspiration:
# https://github.com/tobiasmcnulty/amzscraper
# https://chase-seibert.github.io/blog/2011/01/15/backup-your-amazon-order-history-with-python.html

class AmazonDeScraper(AmazonScraper):
    TLD: Final[str] = "de"
    ORDER_LIST_URL: Final[str] = AmazonScraper.ORDER_LIST_URL_DICT[TLD]
    ORDER_DETAIL_URL: Final[str] = AmazonScraper.ORDER_DETAIL_URL_DICT[TLD]

    #ORDER_TRACKING_URL: Final[str] = 'https://track.aliexpress.com/logisticsdetail.htm?tradeId={}'

    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options)
        self.command = command
        self.cache_orderlist = options['cache_orderlist']
        self.log = self.setup_logger(logging.getLogger(__name__))
        if options['year'] != -1 and \
            (options['year'] > datetime.date.today().year or options['year'] < 2011):
            self.log.critical(
                "--year must be from %s to %s inclusive, or -1",
                2011, datetime.date.today().year)
            raise CommandError("Invalid --year")
        self.scrape_year = options['year']

    def command_scrape(self) -> None:
        # https://www.amazon.de/-/en/gp/css/order-history?ref_=nav_orders_first
        pass
