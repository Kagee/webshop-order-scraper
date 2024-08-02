import contextlib
import datetime
import re
import sys
from datetime import datetime as dtdt
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from .base import BaseScraper
from .utils import AMBER


class EbayScraper(BaseScraper):
    # Scrape comand and __init__
    name = "eBay"
    tla = "EBY"
    simple_name = "ebay"

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your eBay orders.
        """
        self.aspects = {}
        order_list_data = self.browser_scrape_or_load_order_list_data()
        self.log.debug("Processing %s order ids...", len(order_list_data))
        self.write(self.ORDER_LIST_JSON_FILENAME, order_list_data, to_json=True)
        orders = {}
        for order_id in order_list_data:
            # One page may contain multiple orders
            if order_id not in orders:
                page_orders = self.browser_scrape_order_page(
                    order_id,
                    order_list_data,
                )
                for page_order_id, order in page_orders.items():
                    orders[page_order_id] = order
        self.pprint(self.aspects)

    def browser_scrape_order_page(
        self,
        order_id: str,
        order_list_data: list,
    ) -> dict:
        order_json_file_path = self.file_order_json_path(order_id)
        if (
            self.can_read(order_json_file_path)
            and not self.options.force_web_scrape
        ):
            self.log.info("Skipping order id %s as it is cached", order_id)
            return self.read(order_json_file_path, from_json=True)

        order_url = order_list_data[order_id]["url"]

        self.log.info("Order id %s is not cached", order_id)
        self.log.info("Order URL %s", order_url)
        self.browser_visit_page_v2(order_url)

        (
            order_delivery_address,
            order_total,
            order_payment_lines,
        ) = self.browser_get_order_summary_data()

        orders = {}
        orderbox: WebElement
        for orderbox in self.b.find_elements(
            By.CSS_SELECTOR,
            ".order-box",
        ):
            (
                order_id,
                order_date,
                orderinfo,
            ) = self.browser_get_order_base_info(orderbox)

            if not order_id or not order_date:
                msg = (
                    "Failed to find expected order id "
                    f"or order date on {order_url}"
                )
                raise ValueError(msg)
            order_json_file_path = self.file_order_json_path(order_id)
            if (
                self.can_read(order_json_file_path)
                and not self.options.force_web_scrape
            ):
                # We check again since order pages can contain multiple orders
                self.log.debug("Skipping order id %s as it is cached", order_id)
                continue
            if order_id in orders:
                msg = f"Order ID {order_id} parsed twice on {order_url}?"
                raise ValueError(msg)

            orders[order_id] = {
                "id": order_id,
                "url": order_list_data[order_id]["url"],
                "total": order_total,
                "date": order_date,
                "orderinfo": orderinfo,
                "payment_lines": order_payment_lines,
                "deliver_address": order_delivery_address,
                "extra_data": {},
            }

            csss = ".order-level-actions-item button"
            tax_invoice_button = None
            with contextlib.suppress(NoSuchElementException):
                tax_invoice_button = orderbox.find_element(
                    By.CSS_SELECTOR,
                    csss,
                )
            if not tax_invoice_button:
                self.log.warning("No tax invoice on order %s", order_id)
            else:
                if tax_invoice_button.text != "View tax invoice":
                    msg = (
                        "tax_invoice_button has wrong text: "
                        f"{tax_invoice_button.text}"
                    )
                    raise ValueError(msg)

                self.b.execute_script(
                    "window.scrollTo(0,arguments[0])",
                    tax_invoice_button,
                )

                tax_invoice_button.click()
                # Tax invoice should be open

                csss = ".print-oly .bar-sections dl"
                label_map = {
                    "Order subtotal": "subtotal",
                    "Postage": "shipping",
                    "VAT": "tax",
                    "Order total": "total",
                }

                def clean_value(value: str) -> dict:
                    if "(" in value:
                        # NOK 19.26 (US $2.28)
                        value = re.match(r"[^\(]*\(([^\)]*)\)", value).group(1)
                    return self.get_value_currency("", value)

                for dl in self.b.find_elements(
                    By.CSS_SELECTOR,
                    csss,
                ):
                    ActionChains(self.b).scroll_to_element(
                        dl,
                    ).perform()
                    label, value = self.dl_to_dt_dd_text(dl)

                    if label in label_map:
                        orders[order_id][label_map[label]] = clean_value(value)
                        self.log.debug(
                            "%s: %s",
                            label,
                            orders[order_id][label_map[label]],
                        )
                    elif label == "Discount":
                        label, value = self.dl_to_dt_dd_text(dl)
                        orders[order_id]["extra_data"]["discount"] = value
                    else:
                        msg = f"Unknown tax invoice label: {label}: {value}"
                        raise ValueError(msg)

                # once finised, scroll to and click
                modal_close_button = self.b.find_element(
                    By.CSS_SELECTOR,
                    "#modal-back-button",
                )
                ActionChains(self.b).scroll_to_element(
                    modal_close_button,
                ).perform()
                modal_close_button.click()

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
            orders[order_id]["items"] = order_list_data[order_id]["items"]

            self.log.debug("Saving order %s to disk", order_id)
            self.write(order_json_file_path, orders[order_id], to_json=True)

        return orders

    def browser_get_order_base_info(self, orderbox):
        order_info_dl: WebElement
        orderinfo = {}
        for order_info_dl in orderbox.find_elements(
            By.CSS_SELECTOR,
            ".order-info dl",
        ):
            dt, dd = self.dl_to_dt_dd_text(order_info_dl)
            self.log.debug("%s: %s", dt, dd)
            if dt == "Order number":
                self.log.debug("Order ID: %s", dd)
                order_id = dd
                continue
            if dt == "Time placed":
                order_date = datetime.datetime.strptime(  # noqa: DTZ007 (unknown timezone)
                    dd,
                    # Mar 14, 2021 at 3:17 PM
                    "%b %d, %Y at %I:%M %p",
                )
                continue
            orderinfo[dt] = dd
        self.log.debug("Order info: %s", orderinfo)
        return order_id, order_date, orderinfo

    def browser_get_order_summary_data(self) -> (str, dict, list):
        csss = ".summary-region .delivery-address-content p"
        order_delivery_address = "\n".join(
            [p.text for p in self.b.find_elements(By.CSS_SELECTOR, csss)],
        )
        self.log.debug("Delivery address: %s", order_delivery_address)
        csss = ".summary-region .order-summary-total dd"
        order_total = self.get_value_currency(
            "total",
            self.b.find_element(By.CSS_SELECTOR, csss).text,
        )
        self.log.debug("Order total: %s", order_total)

        csss = ".summary-region .payment-line-item dl"
        order_payment_lines = []
        for dl in self.b.find_elements(By.CSS_SELECTOR, csss):
            dt = dl.find_element(By.CSS_SELECTOR, "dt").text
            dd = dl.find_element(By.CSS_SELECTOR, "dd").text
            order_payment_lines.append((dt, dd))
        self.log.debug("Order payment lines: %s", order_payment_lines)
        return order_delivery_address, order_total, order_payment_lines

    def download_item_page(self, order_id, item_id):
        item_pdf_file = None
        if self.options.skip_item_pdf:
            return item_pdf_file
        item_url = self.ITEM_PAGE.format(item_id=item_id)
        self.log.debug("Item url for item %s is %s", item_id, item_url)
        order_page_handle = self.b.current_window_handle
        self.b.switch_to.new_window("tab")

        self.browser_visit_page_v2(item_url)
        if (
            "Error Page" in self.b.title
            or (
                "The item you selected is unavailable"
                ", but we found something similar."
            )
            in self.b.page_source
        ):
            item_pdf_file = self.file_item_pdf(
                order_id,
                item_id,
            ).with_suffix(
                ".missing",
            )
            self.write(
                item_pdf_file,
                "1",
            )
            self.log.debug(
                "Item page is error page %s",
                item_id,
            )
            item_pdf_file = None
        else:
            item_pdf_file = self.file_item_pdf(
                order_id,
                item_id,
            )
            self.log.debug(item_pdf_file)
            self.browser_cleanup_and_print_item_page(item_id, item_pdf_file)
        self.b.close()  # item_url
        self.b.switch_to.window(order_page_handle)
        return item_pdf_file

    def browser_cleanup_and_print_item_page(self, item_id, item_pdf_file):
        self.log.debug(
            "Start of item %s cleanup",
            item_id,
        )
        item_page_handle = self.b.current_window_handle

        try:
            item_title_element = self.b.find_element(
                By.CSS_SELECTOR,
                ".x-item-title",
            )
        except NoSuchElementException:
            item_title_element = None
        if item_title_element:
            item_title = item_title_element.text
            item_desc_src = self.b.find_element(
                By.ID,
                "desc_ifr",
            ).get_attribute("src")
            csss = ".filmstrip button img"
            image_elements = self.b.find_elements(
                By.CSS_SELECTOR,
                csss,
            )
            image_urls = [
                re.sub(
                    r"l\d*\.(webp|jpg|jpeg|png)",
                    "l1600.jpeg",
                    (
                        image.get_attribute("src")
                        or image.get_attribute("data-src")
                    ),
                )
                for image in image_elements
            ]
            self.log.info("Title: %s", item_title)
            self.log.info("Image urls: %s", image_urls)
            self.log.info("Iframe: %s", item_desc_src)
            self.b.switch_to.new_window("tab")
            self.browser_visit_page_v2(item_desc_src)
            self.b.execute_script(
                """
                    let body = document.body
                    let h1 = document.createElement("h1")
                    h1.textContent = arguments[0]
                    h1.style.textAlign = "center"
                    let h3 = document.createElement("h3")
                    h3.textContent = arguments[1]
                    h3.style.textAlign = "center"

                    body.prepend(h3)
                    body.prepend(h1)
                    for (
                            let i = 0;
                            i < arguments[2].length;
                            i++
                        ) {
                        img = document.createElement("img")
                        img.src = arguments[2][i];
                        img.style.maxWidth = "90%";
                        body.appendChild(img)
                    }
                    document.querySelectorAll('*')\
                    .forEach(function(e){
                        e.style.fontFamily = "sans-serif";
                        e.style.margin = "0";
                        e.style.padding = "0";
                    });
                    """,
                item_title,
                item_title,
                image_urls,
            )

        self.log.debug("Printing page to PDF")
        self.remove(self.cache["PDF_TEMP_FILENAME"])

        self.b.execute_script("window.print();")
        self.wait_for_stable_file(
            self.cache["PDF_TEMP_FILENAME"],
        )
        self.move_file(
            self.cache["PDF_TEMP_FILENAME"],
            item_pdf_file,
        )

        if self.b.current_window_handle != item_page_handle:
            self.b.close()
        self.b.switch_to.window(item_page_handle)

    def browser_scrape_or_load_order_list_data(self) -> dict:
        order_list_data = {}
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
                    # We load based on a glob so we in theory can find files
                    # thatare older than the oldest in self.file_order_list_year
                    self.log.debug(
                        "Found order list for %s",
                        path.name.split(".")[0],
                    )
                    order_list_data.update(self.read(path, from_json=True))

                return order_list_data
        # Not using cached orderlist
        return self.browser_scrape_order_list_data(order_list_data)

    def browser_scrape_order_list_data(self, order_list_data: dict) -> dict:
        for keyword, year in self.filter_keyword_list():
            json_file = self.file_order_list_year(year)
            # %253A -> %3A -> :
            # https://www.ebay.com/mye/myebay/purchase?filter=year_filter%253ATWO_YEARS_AGO
            self.log.debug("We need to scrape order list for %s", year)
            url = f"https://www.ebay.com/mye/myebay/purchase?filter=year_filter:{keyword}"
            self.log.debug("Scraping order data from %s", url)
            self.browser_visit_page_v2(url)
            # loop all order cards
            orders = {}
            csss = ".m-order-card"
            for order_card in self.browser.find_elements(By.CSS_SELECTOR, csss):
                # .m-order-card .secondaryMessage .primary__item--wrapper
                order_id = order_date = order_total = None
                csss = ".secondaryMessage .primary__item--wrapper"
                for pitem in order_card.find_elements(By.CSS_SELECTOR, csss):
                    spans = pitem.find_elements(
                        By.CSS_SELECTOR,
                        ".primary__item--item-text",
                    )
                    label = spans[0].text
                    value = spans[1].text
                    if label.startswith("Order number"):
                        order_id = value
                    elif label.startswith("Order total"):
                        order_total = self.get_value_currency("total", value)
                    elif label.startswith("Order date"):
                        order_date = datetime.datetime.strptime(  # noqa: DTZ007 (unknown timezone)
                            value,
                            # Feb 11, 2017
                            "%b %d, %Y",
                        )
                    else:
                        msg = f"Unexpected order label: {label} {value}"
                        raise ValueError(msg)
                if not all([order_id, order_date, order_total]):
                    msg = (
                        "Missing order id/date/total: "
                        f"{order_id}/{order_date}/{order_total}"
                    )
                    raise ValueError(msg)

                xpath = ".//a[text()='View order details']"
                order_details_a = order_card.find_element(By.XPATH, xpath)
                order = {
                    "id": order_id,
                    "date": order_date,
                    "total": order_total,
                    "url": order_details_a.get_attribute("href"),
                    "items": [],
                }

                for item_card in order_card.find_elements(
                    By.CSS_SELECTOR,
                    ".m-item-card",
                ):
                    item_id = None
                    for div in item_card.find_elements(By.TAG_NAME, "div"):
                        if item_id := div.get_attribute("input-listing-id"):
                            break
                    item = {
                        "id": item_id,
                    }

                    if thumbnail := self.browser_get_item_thumb(
                        order_id,
                        item_id,
                        item_card,
                    ):
                        item["thumbnail"] = thumbnail

                    if pdf := self.browser_get_item_pdf(
                        order_id,
                        item_id,
                    ):
                        item["pdf"] = pdf

                    xpath = './/div[contains(@class, "item-info-title")]/div'
                    item["name"] = item_card.find_element(
                        By.XPATH,
                        xpath,
                    ).text

                    xpath = (
                        ".//div[contains(@class, "
                        '"item-info-additionalPrice")]/div'
                    )
                    item["total"] = self.get_value_currency(
                        "total",
                        item_card.find_element(
                            By.XPATH,
                            xpath,
                        ).text,
                    )

                    xpath = (
                        ".//div[contains(@class, "
                        '"item-info-aspectValuesList")]/div'
                    )

                    def aspect_to_key(aspect):
                        parts = aspect.split(":", 1)
                        label = parts[0].strip()
                        value = parts[1].strip()
                        if label.lower() in ["amount", "quantity"]:
                            # Amount <-> 1 Pcs
                            # Quantity <-> 3
                            v = re.match(r"\d*", value)
                            return "quantity", v.group(0)
                        return "sku", f"{label}: {value}"

                    aspects = item_card.find_elements(By.XPATH, xpath)
                    if len(aspects) == 0:
                        # quantity = 1, no sku
                        item["sku"] = None
                        item["quantity"] = 1
                    else:
                        if order_id not in self.aspects:
                            self.aspects[order_id] = {}
                        if item_id not in self.aspects[order_id]:
                            self.aspects[order_id][item_id] = []
                        self.aspects[order_id][item_id] = [
                            a.text for a in aspects
                        ]
                    """
                    if len(aspects) < 3:  # noqa: PLR2004
                        for aspect in aspects:
                            key, value = aspect_to_key(aspect.text)
                            item[key] = value
                        if "sku" not in item:
                            item["sku"] = None
                        elif "quantity" not in item:
                            item["quantity"] = 1
                    else:
                        msg = "Unexpected aspects (>2): " + str(
                            [a.text for a in aspects],
                        )
                        raise ValueError(msg)
                    """
                    order["items"].append(item)

                orders[order_id] = order
            self.write(json_file, orders, to_json=True)
            order_list_data.update(orders)
        return order_list_data

    def browser_get_item_pdf(self, order_id: str, item_id: str) -> Path | None:
        pdf_file = self.file_item_pdf(order_id, item_id)
        if self.can_read(pdf_file):
            self.log.debug(
                "Found PDF for item %s: %s",
                item_id,
                pdf_file.name,
            )
            return pdf_file
        self.log.debug(
            "Need to make PDF for item %s",
            item_id,
        )
        return self.download_item_page(
            order_id,
            item_id,
        )

    def browser_get_item_thumb(
        self,
        order_id: str,
        item_id: str,
        item_card_element: WebElement,
    ) -> Path | None:
        thumb_file = self.file_item_thumb(order_id, item_id)
        thumb_file.parent.mkdir(exist_ok=True)
        if self.can_read(thumb_file):
            self.log.debug(
                "Found thumbnail for item %s: %s",
                item_id,
                thumb_file.name,
            )
            return thumb_file
        if self.options.skip_item_thumb:
            self.log.debug(
                "Skipping thumbnail for item %s",
                item_id,
            )
            return None
        image_element = item_card_element.find_element(
            By.CSS_SELECTOR,
            ".m-image img",
        )
        thumb_url = image_element.get_attribute("src")
        # Ebay "missing" images
        # https://i.ebayimg.com/images/g/unknown
        # https://i.ebayimg.com/images/g/JuIAAOSwXj5XG5VC/s-l*.webp
        if "unknown" in thumb_url or "JuIAAOSwXj5XG5VC" in thumb_url:
            self.log.debug("No thumnail for item %s", item_id)
            self.write(thumb_file.with_suffix(".missing"), "1")
            return None

        # Download image
        if ".webp" not in thumb_url:
            self.log.warning("Thumnail for %s is not webp, skipping", item_id)
            return None
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
        return thumb_file

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
         and a .zip with all attachments
        """
        structure = self.get_structure(
            self.name,
            None,
            "https://www.ebay.com/vod/FetchOrderDetails?orderId={order_id}",
            "https://www.ebay.com/itm/{item_id}",
        )
        structure["metadata"][
            "comment"
        ] = "Order totals may be wrong on older orders"
        orders = []
        for order_json_handle in self.cache["ORDERS"].glob("**/order.json"):
            self.log.debug("Processing %s", order_json_handle.parent.name)
            order_input = self.read(order_json_handle, from_json=True)
            order = {
                "id": order_input["id"],
                "date": dtdt.strptime(  # noqa: DTZ007
                    order_input["date"],
                    "%Y-%m-%d %H:%M:%S",
                )
                .date()
                .strftime("%Y-%m-%d"),
                "total": order_input["total"],
                "extra_data": order_input["extra_data"],
            }
            order["extra_data"].update(order_input["orderinfo"])
            for payment_line in order_input["payment_lines"]:
                if payment_line[0] == "VAT*":
                    order["tax"] = self.get_value_currency(
                        payment_line[0],
                        payment_line[1],
                    )
                elif payment_line[0] == "Shipping":
                    order["shipping"] = self.get_value_currency(
                        payment_line[0],
                        payment_line[1],
                    )
                elif " item" in payment_line[0]:
                    m = re.match(r"(\d*) items?", payment_line[0])
                    order["extra_data"]["num_items"] = int(m.group(1))
                else:
                    self.log.warning(
                        "Unknown payment: %s: %s",
                        payment_line[0],
                        payment_line[1],
                    )
                    if "payment" not in order["extra_data"]:
                        order["extra_data"]["payment"] = {}
                    order["extra_data"]["payment"][
                        payment_line[0]
                    ] = payment_line[1]
            order["items"] = []
            for item_input in order_input["items"]:
                item = {
                    "id": item_input["id"],
                    "name": item_input["name"],
                    "total": item_input["total"],
                    "quantity": int(item_input["quantity"]),
                    "extra_data": {},
                }
                if "extra_data" in item_input:
                    item["extra_data"] = item_input["extra_data"]

                if "thumbnail" in item_input:
                    item["thumbnail"] = (
                        Path(item_input["thumbnail"])
                        .relative_to(self.cache["BASE"])
                        .as_posix()
                    )
                if "pdf" in item_input:
                    item["attachments"] = []
                    item["attachments"].append(
                        {
                            "name": "Item PDF",
                            "path": (
                                Path(item_input["pdf"])
                                .relative_to(self.cache["BASE"])
                                .as_posix()
                            ),
                        },
                    )

                if "sku" in item_input and item_input["sku"]:
                    item["variation"] = item_input["sku"]
                order["items"].append(item)

            orders.append(order)
        structure["orders"] = orders
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
        self.ITEM_PAGE = "https://www.ebay.com/itm/{item_id}"

    def order_page_url(self, order_id: str) -> str:
        return f"https://www.ebay.com/vod/FetchOrderDetails?orderId={order_id}"

    def file_order_json_path(self, order_id: str) -> Path:
        return self.dir_order_id(order_id) / "order.json"

    def file_item_thumb(
        self,
        order_id: str,
        item_id: str,
        ext: str = "jpg",
    ) -> Path:
        return self.dir_order_id(order_id) / f"item-thumb-{item_id}.{ext}"

    def file_item_pdf(
        self,
        order_id: str,
        item_id: str,
        ext: str = "pdf",
    ) -> Path:
        return self.dir_order_id(order_id) / f"item-{item_id}.{ext}"

    def dir_order_id(self, order_id: str) -> Path:
        return self.cache["ORDERS"] / f"{order_id}/"

    def file_order_list_year(self, year: int) -> Path:
        return self.cache["ORDER_LISTS"] / f"{year}.json"
