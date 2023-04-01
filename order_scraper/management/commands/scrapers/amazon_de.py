from django.conf import settings
# This is used in a Django command
from django.core.management.base import BaseCommand, CommandError
# from django.core.serializers.json import DjangoJSONEncoder

from .base import BaseScraper

class AmazonDeScraper(BaseScraper):
    def __init__(self, command: BaseCommand, cache_orderlist: bool):
        super().__init__(command)
        self.cache_orderlist = cache_orderlist

    def command_scrape(self):
        # https://www.amazon.de/-/en/gp/css/order-history?ref_=nav_orders_first
        print(settings.SCRAPER_AMZDE_PASSWORD)
