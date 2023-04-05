from typing import Dict

from django.core.management.base import BaseCommand

from .base import BaseScraper

# Scraper for trying out code for other scrapers
class TryOutScraper(BaseScraper):
    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options)
        self.log = self.setup_logger(__name__)

    def command_scrape(self):
        self.browser_visit_page("https://hild1.no/", False)

    # No login
    def browser_login(self, url):
        pass
