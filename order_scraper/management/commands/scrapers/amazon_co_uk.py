from typing import Dict, Final

from django.core.management.base import BaseCommand

from .amazon import AmazonScraper


class AmazonCoUkScraper(AmazonScraper):
    TLD: Final[str] = "co.uk"

    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options)
        self.log = self.setup_logger(__name__)
        # pylint: disable=invalid-name
        (self.cache,
         self.PDF_TEMP_FILENAME,
         self.ORDER_LIST_CACHE_FILENAME_TEMPLATE) = self.setup_cache()
