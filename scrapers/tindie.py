# pylint: disable=unused-import
import contextlib
import re
from datetime import datetime as dt
from datetime import datetime as dtdt
from pathlib import Path
from typing import TYPE_CHECKING, Final, List  # noqa: UP035

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from .base import BaseScraper

# pylint: disable=unused-import
from .utils import AMBER

if TYPE_CHECKING:
    from selenium.webdriver.remote.webelement import WebElement


class TindieScraper(BaseScraper):
    tla: Final[str] = "TND"
    name: Final[str] = "Tindie"
    simple_name: Final[str] = "tindie"

    def __init__(self, options: dict):
        super().__init__(options, __name__)
        self.setup_cache(self.simple_name)
        self.setup_templates()

    def command_scrape(self):
        order_dict = self.browser_scrape_order_list()
        for order in order_dict.values():
            self.log.debug("Order id: %s", order["id"])
            for item in order["items"]:
                self.log.debug("Item id: %s", item["id"])
                self.browser_get_item_thumb(item["id"])
                self.verify_pdf(item["id"])

    def verify_pdf(self, item_id: str) -> None:
        item_id_filesafe = item_id.replace("/", "_")
        pdf_path = Path(self.PDFS.format(filename="{item_id_filesafe}.pdf"))
        if not self.can_read(pdf_path):
            url = self.ITEM_URL.format(item_id=item_id)
            msg = (
                f"Please save {url} to PDF using "
                "instructions in bookmarklets/tindie.com.txt"
            )
            self.log.error(msg)
            raise ValueError(msg)

    def browser_scrape_order_list(self) -> dict:  # noqa: PLR0915
        if self.options.use_cached_orderlist and self.can_read(
            self.ORDER_LIST_JSON,
        ):
            order_dict = self.read(self.ORDER_LIST_JSON, from_json=True)
        else:
            order_dict = {}
            _brws = self.browser_visit(
                "https://www.tindie.com/orders/purchases/",
            )
            csss = "main table.table tbody tr"
            order_trs: WebElement = self.find_elements(
                By.CSS_SELECTOR,
                csss,
            )

            for order_tr in order_trs:
                order = {}
                tds: List[WebElement] = order_tr.find_elements(  # noqa: UP006
                    By.TAG_NAME,
                    "td",
                )
                # td1 a.text = #<order_id>
                order["id"] = tds[0].text[1:]
                self.log.debug("Order ID: %s", order["id"])

                # td2.text = order date 27 Jun 2023
                order["date"] = dt.strptime(
                    tds[1].text,
                    "%d %b %Y",
                ).astimezone()
                self.log.debug("Order date: %s", order["date"])

                csss = "div.row"
                item_divs: List[WebElement] = tds[2].find_elements(  # noqa: UP006
                    By.CSS_SELECTOR,
                    csss,
                )
                # td3 div -> order item ->
                #     div (3 stk):

                items = []
                for item_div in item_divs:
                    item = {}
                    item_cols: List[WebElement] = item_div.find_elements(  # noqa: UP006
                        By.TAG_NAME,
                        "div",
                    )
                    #     -div1 <a href="/products/hamstudio/ham-ch552-micro/">Ham CH552 Micro</a>
                    item_a = item_cols[0].find_element(By.TAG_NAME, "a")
                    item["name"] = item_a.text
                    item["id"] = re.sub(
                        "http.*/products/",
                        "",
                        item_a.get_attribute("href"),
                    )[:-1]
                    self.log.debug(
                        "Item id: %s, Item name: %s",
                        item["id"],
                        item["name"],
                    )
                    #     -div2 : ignore?
                    #     -div3: line1: order status, line 2: status date, line x in small: tracking name or url(href)
                    item_tracking_info = []
                    tracking_small_element: WebElement = None
                    with contextlib.suppress(NoSuchElementException):
                        tracking_small_element = item_cols[2].find_element(
                            By.TAG_NAME,
                            "small",
                        )

                        if tracking_small_element:
                            tracking_a: WebElement = None
                            with contextlib.suppress(NoSuchElementException):
                                tracking_a = (
                                    tracking_small_element.find_element(
                                        By.TAG_NAME,
                                        "a",
                                    )
                                )
                            for (
                                line
                            ) in tracking_small_element.text.splitlines():
                                sline = line.strip()
                                if sline and "Track Your Package" not in sline:
                                    item_tracking_info.append(sline)
                            if tracking_a:
                                item_tracking_info.append(
                                    tracking_a.get_attribute("href"),
                                )
                        else:
                            self.log.warning("No tracking info")
                        self.browser.execute_script(
                            """
                                arguments[0].remove();
                            """,
                            tracking_small_element,
                        )
                    item["extra_data"] = {}
                    item["extra_data"]["status"] = " ".join(
                        item_cols[2].text.splitlines(),
                    )
                    self.log.warning(
                        "Item status: %s",
                        item["extra_data"]["status"],
                    )
                    if item_tracking_info:
                        item_tracking_info = "; ".join(item_tracking_info)
                        item["extra_data"]["tracking"] = item_tracking_info
                        self.log.debug(
                            "Item tracking info: %s",
                            item["extra_data"]["tracking"],
                        )
                    items.append(item)
                order["items"] = items
                # td4.text order total $43.00
                order_total = self.get_value_currency("total", tds[3].text)
                self.log.debug("Order total: %s", order_total)
                order_dict[order["id"]] = order

        self.write(self.ORDER_LIST_JSON, order_dict, to_json=True)
        return order_dict

    def browser_get_item_thumb(self, item_id: str):
        item_id_filesafe = item_id.replace("/", "_")
        filename = f"{item_id_filesafe}.jpg"
        image_path = Path(self.THUMBNAILS.format(filename=filename))
        image_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.can_read(image_path):
            self.browser_visit(self.ITEM_URL.format(item_id=item_id))
            img = self.find_element(By.CSS_SELECTOR, "img.product-image")
            thumb_urls = img.get_attribute("data-zoom-srcset")
            thumb_urls = thumb_urls.strip()
            thumb_urls = re.sub(r" [ \n]*", " ", thumb_urls)
            # thumb_urls.split();
            thumb_urls = [
                x.strip() for x in thumb_urls.split(",") if "http" in x
            ]
            thumb_url = thumb_urls[len(thumb_urls) - 1].split(" ")[0]
            self.download_url_to_file(thumb_url, image_path)
            self.log.debug("Thumbnail for %s saved to %s", item_id, image_path)
        else:
            self.log.debug("Thumbnail for %s found", item_id)

    def browser_detect_handle_interrupt(self, _):
        brws = self.browser_get_instance()
        if "login" in brws.current_url:
            self.log.error(
                AMBER(
                    "Please manyally login to Tindie, "
                    "and press ENTER when finished.",
                ),
            )
            input()

    def setup_templates(self):
        # pylint: disable=invalid-name
        self.ORDER_LIST_JSON = self.cache["BASE"] / "order_list.json"
        self.ORDER_FOLDER_TP = str(self.cache["BASE"] / "orders/{order_id}/")
        self.THUMBNAILS = str(self.cache["BASE"] / "thumbnails/{filename}")
        self.PDFS = str(self.cache["BASE"] / "pdfs/{filename}")
        self.ORDER_URL = "https://www.tindie.com/orders/purchases/{order_id}/"
        self.ITEM_URL = "https://www.tindie.com/products/{item_id}/"

    def command_to_std_json(self):
        structure = self.get_structure(
            self.name,
            None,
            "https://www.tindie.com/orders/purchases/{order_id}/",
            "https://www.tindie.com/products/{item_id}",
        )
        orders = []
        for order_input in self.json_read(
            self.ORDER_LIST_JSON,
        ).values():
            self.log.debug(order_input)
            order = {
                "id": order_input["id"],
                "date": dtdt.strptime(
                    order_input["date"],
                    "%Y-%m-%d %H:%M:%S%z",
                )
                .date()
                .strftime("%Y-%m-%d"),
            }
            order["items"] = []
            unique_items = []
            for item_input in order_input["items"]:
                if item_input["id"] in unique_items:
                    continue
                unique_items.append(item_input["id"])
                item = {
                    "id": item_input["id"],
                    "name": item_input["name"],
                    "quantity": 0,
                    "extra_data": {},
                }

                item_id_filesafe = item_input["id"].replace("/", "_")
                pdf_path = Path(
                    self.PDFS.format(filename=f"{item_id_filesafe}.pdf"),
                )
                thumb_path = Path(
                    self.THUMBNAILS.format(filename=f"{item_id_filesafe}.jpg"),
                )
                item["thumbnail"] = (
                    Path(thumb_path).relative_to(self.cache["BASE"]).as_posix()
                )
                item["attachements"] = []
                item["attachements"].append(
                    {
                        "name": "Item PDF",
                        "path": (
                            Path(pdf_path)
                            .relative_to(self.cache["BASE"])
                            .as_posix()
                        ),
                    },
                )

                order["items"].append(item)
            orders.append(order)
        structure["orders"] = orders
        import pprint

        self.log.debug(pprint.pformat(structure))
        self.output_schema_json(structure)
