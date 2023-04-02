from typing import Dict, Final

from django.core.management.base import BaseCommand

from .amazon import AmazonScraper


class AmazonCoJpScraper(AmazonScraper):
    TLD: Final[str] = "co.jp"

    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options)
        self.log = self.setup_logger(__name__)
        # pylint: disable=invalid-name
        (self.cache,
         self.PDF_TEMP_FILENAME,
         self.ORDER_LIST_CACHE_FILENAME_TEMPLATE,
         self.ORDER_LIST_JSON_FILENAME_TEMPLATE) = self.setup_cache()
