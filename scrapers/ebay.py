import datetime
import time
from pathlib import Path

from selenium.webdriver.common.by import By

from . import settings  # noqa: F401
from .base import BaseScraper
from .utils import AMBER


class EbayScraper(BaseScraper):
    # Scrape comand and __init__
    name = "eBay"
    tla = "EBY"

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your eBay orders.
        """
        order_ids = self.browser_load_order_list()
        self.log.debug("Processing %s order ids", len(order_ids))
        self.write(self.ORDER_LIST_JSON_FILENAME, order_ids, to_json=True)

    def browser_load_order_list(self) -> list:
        if self.options.use_cached_orderlist:
            if self.can_read(self.ORDER_LIST_JSON_FILENAME):
                self.log.info("Using cached orderlist.")
                return self.read(self.ORDER_LIST_JSON_FILENAME, from_json=True)
            self.log.info("Could not find cached orderlist.")

        order_ids = []
        for keyword, year in self.filter_keyword_list():
            json_file = self.file_order_list_year(year)
            if self.can_read(json_file):
                self.log.debug("Found order list for %s", year)
                order_ids += self.read(json_file, from_json=True)
                continue
            # %253A -> %3A -> :
            # https://www.ebay.com/mye/myebay/purchase?filter=year_filter%253ATWO_YEARS_AGO
            self.log.debug("We need to scrape order list for %s", year)
            url = f"https://www.ebay.com/mye/myebay/purchase?filter=year_filter:{keyword}"
            self.log.debug(url)
            self.browser_visit_page_v2(url)
            # Find all order numbers
            xpath = "//span[text()='Order number:']/following-sibling::span"
            span_elements = self.browser.find_elements(By.XPATH, xpath)
            year_order_ids = [
                span_element.text for span_element in span_elements
            ]
            self.write(json_file, year_order_ids, to_json=True)
            order_ids += year_order_ids
        return order_ids

    def filter_keyword_list(self):
        now = datetime.datetime.now().astimezone()
        year = int(now.strftime("%Y"))
        return [
            (
                "CURRENT_YEAR",
                year,
            ),
            (
                "LAST_YEAR",
                year - 1,
            ),
            (
                "TWO_YEARS_AGO",
                year - 2,
            ),
            (
                "THREE_YEARS_AGO",
                year - 3,
            ),
            (
                "FOUR_YEARS_AGO",
                year - 4,
            ),
            (
                "FIVE_YEARS_AGO",
                year - 5,
            ),
            (
                "SIX_YEARS_AGO",
                year - 6,
            ),
            (
                "SEVEN_YEARS_AGO",
                year - 7,
            ),
        ]

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        brws = self.browser_get_instance()
        if "login" in brws.current_url:
            self.log.error(
                AMBER(
                    "Please manyally login to eBay, "
                    "and press ENTER when finished.",
                ),
            )
            input()
            if brws.current_url != expected_url:
                self.browser_visit_page_v2(
                    expected_url,
                )

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with schema,
         and a .zip with all attachements
        """
        structure = self.get_structure(  # noqa: F841
            self.name,
            None,
            "https://www.ebay.com/vod/FetchOrderDetails?orderId={order_id}",
            "https://www.ebay.com/itm/{item_id}",
        )

        # structure["orders"] = orders
        self.output_schema_json(structure)

    def __init__(self, options: dict):
        super().__init__(options, __name__)
        self.setup_cache("ebay")
        self.setup_templates()
        self.browser = None

    # Utility functions
    def setup_cache(self, base_folder: Path):
        # self.cache BASE / ORDER_LISTS / ORDERS /
        # TEMP / PDF_TEMP_FILENAME / IMG_TEMP_FILENAME
        super().setup_cache(base_folder)

    def setup_templates(self):
        self.ORDER_LIST_START = "https://www.ebay.com/mye/myebay/purchase"
        self.ORDER_LIST_JSON_FILENAME = (
            self.cache["ORDER_LISTS"] / "order_list.json"
        )

    def dir_order_id(self, order_id):
        return self.cache["ORDERS"] / f"{order_id}/"

    def file_order_list_year(self, year):
        return self.cache["ORDER_LISTS"] / f"{year}.json"
