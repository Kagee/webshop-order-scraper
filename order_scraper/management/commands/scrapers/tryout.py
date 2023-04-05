
import os
from pathlib import Path
from typing import Dict

from django.conf import settings
from django.core.management.base import BaseCommand

from .base import BaseScraper


# Scraper for trying out code for other scrapers
class TryOutScraper(BaseScraper):
    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options)
        self.log = self.setup_logger(__name__)
        self.setup_cache()

    def command_scrape(self):
        self.browser_visit_page("https://hild1.no/", False)

    def setup_cache(self):
        
        self.cache: Dict[str, Path] = {
            "BASE": (Path(settings.SCRAPER_CACHE_BASE) / 
                     Path('tryout')).resolve()
        }
        for (name, path) in self.cache.items():  # pylint: disable=consider-using-dict-items
            self.log.debug("Cache folder %s: %s", name, path)
            self.makedir(path)

        self.PDF_TEMP_FOLDER: Path = self.cache['BASE'] / Path('temporary-pdf/')
        self.makedir(self.PDF_TEMP_FOLDER)

        self.PDF_TEMP_FILENAME: Path = self.PDF_TEMP_FOLDER / Path('temporary-pdf.pdf')

    # No login
    def browser_login(self, url):
        pass
