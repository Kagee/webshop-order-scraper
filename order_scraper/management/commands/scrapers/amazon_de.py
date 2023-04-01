from django.core.management.base import BaseCommand, CommandError

from .base import BaseScraper

class AmazonDeScraper(BaseScraper):
    def __init__(self, command: BaseCommand, cache_orderlist: bool):
        super().__init__(command)
        self.cache_orderlist = cache_orderlist
        raise CommandError('Scraping of Amazon (DE) not yet implemented')

    def command_scrape(self):
        pass
