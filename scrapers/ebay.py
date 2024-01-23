import datetime
import pprint
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

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
        self.log.debug("Processing %s order ids...", len(order_ids))
        self.write(self.ORDER_LIST_JSON_FILENAME, order_ids, to_json=True)
        orders = {}
        for order_id, order_url in sorted(order_ids):
            if order_id not in ["11-06736-46406", "03-06607-27879"]:
                # while developing, only parse one order
                # return, might fail #/
                continue
            # if order_id not in ["230443738010"]:  # ["10-06606-54233"]:
            #    continue

            if order_id in orders:
                # Order pages may contain multiple order ids,
                # and may already have been scraped
                continue
            page_orders = self.browser_scrape_order_id(order_id, order_url)
            for page_order_id, order in page_orders.items():
                orders[page_order_id] = order
        pp = pprint.PrettyPrinter(depth=6)
        self.log.debug(pp.pformat(orders))

    def browser_scrape_order_id(self, order_id: str, order_url: str) -> dict:
        json_file = self.file_order_id_json(order_id)
        if self.can_read(json_file):
            self.log.debug("Skipping order id %s as it is cached")
        self.browser_visit_page_v2(order_url)

        csss = ".summary-region .delivery-address-content p"
        order_delivery_address = "\n".join(
            [p.text for p in self.b.find_elements(By.CSS_SELECTOR, csss)],
        )
        self.log.debug("Delivery address: %s", order_delivery_address)
        csss = ".summary-region .order-summary-total dd"
        order_total = self.b.find_element(By.CSS_SELECTOR, csss).text
        self.log.debug("Order total: %s", order_total)

        csss = ".summary-region .payment-line-item dl"
        order_payment_lines = []
        for dl in self.b.find_elements(By.CSS_SELECTOR, csss):
            dt = dl.find_element(By.CSS_SELECTOR, "dt").text
            dd = dl.find_element(By.CSS_SELECTOR, "dd").text
            order_payment_lines.append((dt, dd))
        self.log.debug("Order payment lines: %s", order_payment_lines)

        orders = {}
        orderbox: WebElement
        for orderbox in self.b.find_elements(
            By.CSS_SELECTOR,
            ".order-box",
        ):
            order_id = None
            order_date = None
            orderinfo = {}
            order_info_dl: WebElement
            for order_info_dl in orderbox.find_elements(
                By.CSS_SELECTOR,
                ".order-info dl",
            ):
                dt = order_info_dl.find_element(By.CSS_SELECTOR, "dt").text
                dd = order_info_dl.find_element(By.CSS_SELECTOR, "dd").text
                self.log.debug("%s: %s", dt, dd)
                if dt == "Order number":
                    self.log.debug("Order ID: %s", dd)
                    order_id = dd
                    continue
                if dt == "Time placed":
                    order_date = (
                        datetime.datetime.strptime(  # noqa: DTZ007 (unknown timezone)
                            dd,
                            # Mar 14, 2021 at 3:17 PM
                            "%b %d, %Y at %I:%M %p",
                        ),
                    )
                orderinfo[dt] = dd
            self.log.debug("Order info: %s", orderinfo)

            if not order_id or not order_date:
                msg = (
                    "Failed to find expected order id "
                    f"or order date on {order_url}"
                )
                raise ValueError(msg)
            if order_id in orders:
                msg = f"Order ID {order_id} parsed twice on {order_url}?"
                raise ValueError(msg)

            orders[order_id] = {
                "id": order_id,
                "total": order_total,
                "date": order_date,
                "orderinfo": orderinfo,
                "payment_lines": order_payment_lines,
                "deliver_address": order_delivery_address,
                "extra_data": {},
            }
            si = orderbox.find_element(By.CSS_SELECTOR, ".shipment-info")
            status = "Unknown"
            status_title = si.find_element(
                By.CSS_SELECTOR,
                ".shipment-card-sub-title",
            )
            if status_title and status_title.text != "":
                status = status_title.text
            orders[order_id]["extra_data"]["tracking_status"] = status
            tracking_infos = si.find_elements(
                By.CSS_SELECTOR,
                ".shipment-card-content .tracking-box .tracking-info dl",
            )

            # Number, Shipping Service, Carrier
            for tracking_info in tracking_infos:
                if "shipping" not in orders[order_id]["extra_data"]:
                    orders[order_id]["extra_data"]["shipping"] = {}
                orders[order_id]["extra_data"]["shipping"][
                    tracking_info.find_element(By.CSS_SELECTOR, "dt").text
                ] = tracking_info.find_element(By.CSS_SELECTOR, "dd").text

            orders[order_id]["extra_data"]["progress_status"] = [
                item.get_attribute("aria-label")
                for item in si.find_elements(
                    By.CSS_SELECTOR,
                    ".shipment-card-content .progress-stepper__item",
                )
            ]
            orders[order_id]["items"] = []
            item_card_element: WebElement
            for item_card_element in si.find_elements(
                By.CSS_SELECTOR,
                ".item-container .item-card",
            ):
                item = {
                    "extra_data": {},
                }
                desc: WebElement = item_card_element.find_element(
                    By.CSS_SELECTOR,
                    ".card-content-description .item-description a",
                )
                item["name"] = desc.text
                item_id = desc.get_attribute("href").split("/")
                item["id"] = item_id = item_id[len(item_id) - 1]

                thumb_file = self.file_item_thumb(order_id, item_id)
                if self.can_read(thumb_file):
                    self.log.debug(
                        "Found thumbnail for item %s: %s",
                        item_id,
                        thumb_file.name,
                    )
                    item["thumbnail"] = thumb_file
                else:
                    image_element = item_card_element.find_element(
                        By.CSS_SELECTOR,
                        ".card-content-image-box img",
                    )
                    thumb_url = image_element.get_attribute("src")
                    # Ebay "missing" images
                    # https://i.ebayimg.com/images/g/unknown
                    # https://i.ebayimg.com/images/g/JuIAAOSwXj5XG5VC/s-l*.webp
                    if (
                        "unknown" in thumb_url
                        or "JuIAAOSwXj5XG5VC" in thumb_url
                    ):
                        self.log.debug("No thumnail for item %s", item_id)
                        self.write(thumb_file.with_suffix("missing"), 1)
                    else:
                        # Download image
                        if ".webp" not in thumb_url:
                            msg = f"Thumnail for {item_id} is not webp"
                            raise ValueError(msg)
                        thumb_url = re.sub(
                            r"l\d*\.webp",
                            "l1600.webp",
                            thumb_url,
                        )
                        self.log.debug("Thumbnail url: %s", thumb_url)
                        self.download_url_to_file(
                            thumb_url,
                            thumb_file,
                        )
                        item["thumbnail"] = thumb_file
                # Thumbnail done
                csss = ".item-description .item-price"
                item["total"] = item_card_element.find_element(
                    By.CSS_SELECTOR,
                    csss,
                ).text
                csss = ".item-aspect-value"
                item_aspect_values = item_card_element.find_elements(
                    By.CSS_SELECTOR,
                    csss,
                )
                num_iav = len(item_aspect_values)
                if num_iav == 3:
                    item["sku"] = item_aspect_values[1].text
                    item["extra_data"]["return_window"] = " ".join(
                        set(item_aspect_values[2].text.split("\n")),
                    )
                elif num_iav == 2:
                    item["extra_data"]["return_window"] = item_aspect_values[
                        1
                    ].text
                    item["sku"] = None

                #                    .item-card (N)
                #                        .card-content-description
                #                            .item-description
                #                                 .item-price -> TOTAL!
                #                            .item-aspect-values-list
                #                                  .item-aspect-value (N) ->
                #                                   if 2 itemnum + return,
                #                                   1: item numder
                #                                   2: SKU?
                #                                   3: return window?
            orders[order_id]["items"].append(item)
            # save order to json when done with items

        return orders

    def browser_load_order_list(self) -> list:
        order_ids = []
        if self.options.use_cached_orderlist:
            files = list(
                self.cache["ORDER_LISTS"].glob(
                    "[0-9][0-9][0-9][0-9].json",
                ),
            )
            if not files:
                self.log.error(
                    "No cached order lists found, "
                    "try witout --use-cached-orderlists",
                )
                sys.exit(1)
            else:
                for path in sorted(files):
                    # We load based on a glob so we in theory can find files that
                    # are older than the oldest in self.file_order_list_year
                    self.log.debug(
                        "Found order list for %s",
                        path.name.split(".")[0],
                    )
                    order_ids += self.read(path, from_json=True)

                return order_ids

        for keyword, year in self.filter_keyword_list():
            json_file = self.file_order_list_year(year)
            # %253A -> %3A -> :
            # https://www.ebay.com/mye/myebay/purchase?filter=year_filter%253ATWO_YEARS_AGO
            self.log.debug("We need to scrape order list for %s", year)
            url = f"https://www.ebay.com/mye/myebay/purchase?filter=year_filter:{keyword}"
            self.log.debug("Scraping order ids from %s", url)
            self.browser_visit_page_v2(url)
            # Find all order numbers
            xpath = "//a[text()='View order details']"
            span_elements = self.browser.find_elements(By.XPATH, xpath)
            year_order_ids = [
                (
                    parse_qs(
                        urlparse(span_element.get_attribute("href")).query,
                    )
                    .pop("orderId")[0]
                    .split("!")[0],
                    span_element.get_attribute("href"),
                )
                for span_element in span_elements
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
        if "login" in self.b.current_url or "signin" in self.b.current_url:
            self.log.error(
                AMBER(
                    "Please manyally login to eBay, "
                    "and press ENTER when finished.",
                ),
            )
            input()
            if self.b.current_url != expected_url:
                self.browser_visit_page_v2(
                    expected_url,
                )

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with schema,
         and a .zip with all attachements
        """
        structure = self.get_structure(
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

    def setup_templates(self) -> None:
        self.ORDER_LIST_START = "https://www.ebay.com/mye/myebay/purchase"
        self.ORDER_LIST_JSON_FILENAME = (
            self.cache["ORDER_LISTS"] / "order_list.json"
        )

    def order_page_url(self, order_id: str) -> str:
        return f"https://www.ebay.com/vod/FetchOrderDetails?orderId={order_id}"

    def file_order_id_json(self, order_id: str) -> Path:
        return self.dir_order_id(order_id) / "order.json"

    def file_item_thumb(
        self,
        order_id: str,
        item_id: str,
        ext: str = "jpg",
    ) -> Path:
        return self.dir_order_id(order_id) / f"item-thumb-{item_id}.{ext}"

    def dir_order_id(self, order_id: str) -> Path:
        return self.cache["ORDERS"] / f"{order_id}/"

    def file_order_list_year(self, year: int) -> Path:
        return self.cache["ORDER_LISTS"] / f"{year}.json"
