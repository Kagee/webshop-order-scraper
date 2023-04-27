import base64
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List

import jsonschema
from lxml.etree import tostring
from lxml.html import HtmlElement
from lxml.html.soupparser import fromstring
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoAlertPresentException,
    NoSuchElementException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from . import settings
from .base import BaseScraper

# pylint: disable=unused-import
from .utils import AMBER, BLUE, GREEN, RED


class AliExpressScraper(BaseScraper):
    tla: Final[str] = "ALI"
    name: Final[str] = "Aliexpress"
    simple_name: Final[str] = "aliexpress"

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with ../schema.json,
         and a .zip with all attachements
        """
        structure = self.get_structure(
            self.name,
            None,
            "https://www.aliexpress.com/p/order/detail.html?orderId={order_id}",
            "https://www.aliexpress.com/item/{item_id}.html",
        )

        raw_orders = []
        for json_order_file in self.cache["ORDERS"].glob("**/*.json"):
            oob = self.read(json_order_file, from_json=True)
            order_obj = {
                "id": oob["id"],
                "date": (
                    datetime.fromisoformat((oob["date"])).date().isoformat()
                ),
                "items": [],
            }
            for price_name, price_value in oob["price_items"].copy().items():
                if price_name.lower() in [
                    "total",
                    "tax",
                    "subtotal",
                    "shipping",
                ]:
                    del oob["price_items"][price_name]
                    order_obj[price_name.lower()] = self.get_value_currency(
                        price_name, price_value
                    )

            if not oob["price_items"]:
                del oob["price_items"]
            if "total" in order_obj:
                del oob["total"]
            else:
                raise NotImplementedError("Total not from price_items")

            del oob["tracking"]
            del oob["id"]
            del oob["contact_info"]
            # We do not delete date, since it in theory is a timestamp
            # del oob["date"]
            # TODO: add cache_file and tracking_cache_file
            del oob["tracking_cache_file"]
            del oob["cache_file"]

            for item_sku_id, item_obj in oob["items"].items():
                nio = {
                    "id": item_sku_id.split("-")[0],
                    "name": item_obj["title"],
                    "variation": item_obj["sku"],
                    "quantity": item_obj["count"],
                    "price": self.get_value_currency(
                        "price", item_obj["price"]
                    ),
                }

                order_obj["items"].append(nio)
                del oob["items"][item_sku_id]["price"]
                del oob["items"][item_sku_id]["sku"]
                del oob["items"][item_sku_id]["count"]
                del oob["items"][item_sku_id]["title"]
                # TODO: add snapshot / thumbnail
                # del oob["items"][item_sku_id]["snapshot"]
                # del oob["items"][item_sku_id]["thumbnail"]
                self.pprint(item_obj)

            # del oob["items"]
            # self.pprint(oob)
            structure["orders"].append(order_obj)
            break
        # raise NotImplementedError("JSON Export for " + self.name + " is not complete")
        print()
        self.pprint(structure)
        # for _raw_order in raw_orders:
        #    pass
        #    # TODO: Loop raw orders and add to structure
        self.valid_json(structure)
        # self.output_schema_json(structure)

    def setup_templates(self):
        # pylint: disable=invalid-name
        # URL Templates
        self.ORDER_LIST_URL: str = (
            "https://www.aliexpress.com/p/order/index.html"
        )
        self.ORDER_DETAIL_URL: str = (
            "https://www.aliexpress.com/p/order/detail.html?orderId={}"
        )
        self.ORDER_TRACKING_URL: str = (
            "https://track.aliexpress.com/logisticsdetail.htm?tradeId={}"
        )
        self.LOGIN_PAGE_RE: str = r"^https://login\.aliexpress\.com"

        # pylint: disable=invalid-name
        self.SNAPSHOT_FILENAME_TEMPLATE = str(
            self.cache["ORDERS"] / "{order_id}/item-snapshot-{item_id}.{ext}"
        )
        self.THUMB_FILENAME_TEMPLATE = str(
            self.cache["ORDERS"] / "{order_id}/item-thumb-{item_id}.png"
        )
        self.ORDER_FILENAME_TEMPLATE = str(
            self.cache["ORDERS"] / "{order_id}/order.{ext}"
        )
        self.TRACKING_HTML_FILENAME_TEMPLATE = str(
            self.cache["ORDERS"] / "{order_id}/tracking.html"
        )
        self.ORDER_CSV_FILENAME = self.cache["BASE"] / "aliexpress-orders.csv"
        self.ORDER_LIST_FILENAME = self.cache["BASE"] / "order-list.html"

    def lxml_parse_individual_order(self, html, order_id):
        order = {}
        info_rows = html.xpath('//div[contains(@class, "info-row")]')
        for info_row in info_rows:
            text = "".join(info_row.itertext())
            if text.startswith("Payment"):
                order["payment_method"] = (
                    "".join(text.split(":")[1:]).strip().replace("\xa0", " ")
                )
        contact_info_div = html.xpath(
            '//div[contains(@class, "order-detail-info-item")]'
            '[not(contains(@class, "order-detail-order-info"))]'
        )[0]
        order["contact_info"] = list(contact_info_div.itertext())
        order["price_items"] = {}
        for price_item in html.xpath(
            '//div[contains(@class, "order-price-item")]'
        ):
            left = (
                "".join(
                    price_item.xpath('.//span[contains(@class, "left-col")]')[
                        0
                    ].itertext()
                )
                .strip()
                .replace("\xa0", " ")
            )
            right = price_item.xpath('.//span[contains(@class, "right-col")]')
            if not right:
                right = price_item.xpath(
                    './/div[contains(@class, "right-col")]'
                )
            order["price_items"][left] = (
                "".join(right[0].itertext()).strip().replace("\xa0", " ")
            )

        if "items" not in order:
            order["items"] = {}

        for item in html.xpath(
            '//div[contains(@class, "order-detail-item-content-wrap")]'
        ):
            title_item = item.xpath('.//div[contains(@class, "item-title")]')[0]
            info = re.match(
                r".+item/([0-9]+)\.html.*",
                title_item.xpath(".//a")[0].get("href"),
            )

            item_id = info.group(1)
            title = "".join(title_item[0].itertext())
            sku_list = item.xpath('.//div[contains(@class, "item-sku-attr")]')

            if len(sku_list) == 0:
                sku_hash = base64.urlsafe_b64encode(
                    "no-sku".encode("utf-8")
                ).decode("utf-8")
                sku = ""
            else:
                sku = (
                    "".join(sku_list[0].itertext()).strip().replace("\xa0", " ")
                )
                sku_hash = base64.urlsafe_b64encode(sku.encode("utf-8")).decode(
                    "utf-8"
                )

            price_count = (
                "".join(
                    item.xpath('.//div[contains(@class, "item-price")]')[
                        0
                    ].itertext()
                )
                .strip()
                .replace("\xa0", " ")
            )

            (price, count) = price_count.split("x")
            # Remove space .. spacing
            title = re.sub(" +", " ", title.replace("\xa0", " "))
            item_sku_id = f"{item_id}-{sku_hash}"
            if not item_sku_id in order["items"]:
                order["items"][item_sku_id] = {}

            if "thumbnail" not in order["items"]:
                order["items"][item_sku_id]["thumbnail"] = (
                    self.THUMB_FILENAME_TEMPLATE.format(
                        order_id=order_id, item_id=item_sku_id
                    )
                )
            if "snapshot" not in order["items"][item_sku_id]:
                order["items"][item_sku_id]["snapshot"] = {
                    "pdf": Path(
                        self.SNAPSHOT_FILENAME_TEMPLATE.format(
                            order_id=order_id, item_id=item_sku_id, ext="pdf"
                        )
                    ).relative_to(self.cache["BASE"]),
                    "html": Path(
                        self.SNAPSHOT_FILENAME_TEMPLATE.format(
                            order_id=order_id, item_id=item_sku_id, ext="html"
                        )
                    ).relative_to(self.cache["BASE"]),
                }
            order["items"][item_sku_id]["thumbnail"] = str(
                Path(order["items"][item_sku_id]["thumbnail"]).relative_to(
                    self.cache["BASE"]
                )
            )

            order["items"][item_sku_id].update(
                {
                    "title": title.strip().replace("\xa0", " "),
                    "sku": sku,
                    "price": price.strip().replace("\xa0", " "),
                    "count": int(count),
                }
            )
        return order

    def get_individual_order_details(self, orders):
        """
        Will loop though orders (possibly limited by ALI_ORDERS),
        and save thumbnails, PDF and json of data.
        """
        if len(settings.ALI_ORDERS):
            self.log.info(
                "Scraping only order IDs from ALI_ORDERS: %s",
                settings.ALI_ORDERS,
            )
        if len(settings.ALI_ORDERS_SKIP):
            self.log.info(
                "Skipping orders IDs in ALI_ORDERS_SKIP: %s",
                settings.ALI_ORDERS_SKIP,
            )

        if settings.ALI_ORDERS_MAX > 0:
            self.log.info(
                "Scraping only a total of %s orders because of ALI_ORDERS_MAX",
                settings.ALI_ORDERS_MAX,
            )

        if settings.ALI_ORDERS_MAX == -1 and len(settings.ALI_ORDERS) == 0:
            self.log.info("Scraping all order IDs")

        counter = 0
        max_orders_reached = False
        for order in orders:
            if settings.ALI_ORDERS_MAX > 0:
                if counter >= settings.ALI_ORDERS_MAX:
                    if not max_orders_reached:
                        self.log.info(
                            "Scraped %s order, stopping scraping",
                            settings.ALI_ORDERS_MAX,
                        )
                        max_orders_reached = True
                    continue
            if (
                len(settings.ALI_ORDERS)
                and order["id"] not in settings.ALI_ORDERS
            ) or order["id"] in settings.ALI_ORDERS_SKIP:
                self.log.info("Skipping order ID %s", order["id"])
                continue
            counter += 1
            order_cache_dir = self.cache["ORDERS"] / order["id"]
            self.makedir(order_cache_dir)
            json_filename = self.ORDER_FILENAME_TEMPLATE.format(
                order_id=order["id"], ext="json"
            )
            if self.can_read(Path(json_filename)):
                self.log.info("Json for order %s found, skipping", order["id"])
                continue
            self.log.debug("#" * 30)
            self.log.debug("Scraping order ID %s", order["id"])
            order_html: HtmlElement = HtmlElement()  # type: ignore

            order["cache_file"] = self.ORDER_FILENAME_TEMPLATE.format(
                order_id=order["id"], ext="html"
            )
            if self.can_read(order["cache_file"]):
                order_html = fromstring(self.read(order["cache_file"]))
            else:
                order_html = self.browser_scrape_order_details(order)

            order_data = self.lxml_parse_individual_order(
                order_html, order["id"]
            )
            order.update(order_data)

            tracking = self.lxml_parse_tracking_html(
                order, self.get_scrape_tracking_page_html(order)
            )
            order["tracking"] = tracking

            # We do this after all "online" scraping is complete
            self.log.info("Writing order details page to cache")
            self.write(
                order["cache_file"], tostring(order_html).decode("utf-8")
            )

            # Make Paths relative before json
            order["cache_file"] = str(
                Path(order["cache_file"]).relative_to(self.cache["BASE"])
            )

            order["tracking_cache_file"] = str(
                Path(order["tracking_cache_file"]).relative_to(
                    self.cache["BASE"]
                )
            )
            self.write(json_filename, order, to_json=True)
        self.browser_safe_quit()

    def load_order_list_html(self):
        """
        Returns the order list html, eithter from disk
        cache or using Selenium to visit the url.

            Returns:
                order_list_html (str): The HTML from the order list page
        """
        if self.options.use_cached_orderlist and os.access(
            self.ORDER_LIST_FILENAME, os.R_OK
        ):
            self.log.info(
                "Loading order list from cache: %s",
                self.ORDER_LIST_FILENAME,
            )
            return self.read(self.ORDER_LIST_FILENAME)
        else:
            self.log.info("Tried to use order list cache, but found none")
        return self.browser_scrape_order_list_html()

    # Methods that use LXML to extract info from HTML

    def lxml_parse_tracking_html(
        self, order: Dict, html: HtmlElement
    ) -> Dict[str, Any]:
        """
        Uses LXML to extract useful info from the HTML this order's tracking page

            Returns:
                tracking (Dict[str, Any]): Dict with tracking info
        """
        tracking = {}
        if len(html.xpath('.//div[@class="tracking-module"]')) == 0:
            self.log.info("Order #%s has no tracking", order["id"])
            return {}
        info = re.match(
            r".+mailNoList=([A-Za-z0-9,]+)",
            html.xpath(
                '//a[contains(@href, "global.cainiao.com/detail.htm")]/@href'
            )[0],
        )
        if info:
            tracking["numbers"] = info.group(1).split(",")
        service_upgraded = html.xpath('.//div[@class="service-upgraded"]')
        tracking["upgrade"] = None
        if len(service_upgraded):
            tracking["upgrade"] = service_upgraded[0].xpath(
                './/div[@class="service-item-flex"]/span/text()'
            )[0]
        shipper_div = html.xpath('//span[contains(@class, "title-eclp")]')[0]
        tracking["shipper"] = (
            shipper_div.text.strip().replace("\xa0", " ")
            if shipper_div is not None
            else "Unknown"
        )
        status_div = html.xpath('//div[contains(@class, "status-title-text")]')[
            0
        ]
        tracking["status"] = (
            status_div.text.strip().replace("\xa0", " ")
            if status_div is not None and status_div.text is not None
            else "Unknown"
        )
        addr = []
        for p_element in html.xpath(
            '//div[contains(@class, "address-detail")]/p'
        ):
            # Join and remove double spaces
            addr.append(" ".join("".join(p_element.itertext()).split()))
        tracking["addr"] = addr
        tracking["shipping"] = []
        for step in html.xpath('//ul[contains(@class, "ship-steps")]/li'):
            ship_time = step.xpath('.//p[contains(@class, "time")]')[0].text
            timezone = step.xpath('.//p[contains(@class, "timezone")]')[0].text
            try:
                head = step.xpath('.//p[contains(@class, "head")]')[0].text
            except IndexError:
                head = ""
            text = "".join(
                step.xpath('.//p[contains(@class, "text")]')[0].itertext()
            )
            tracking["shipping"].append(
                {
                    "time": ship_time,
                    "timezone": timezone,
                    "head": head,
                    "text": text,
                }
            )  # type: ignore
        return tracking

    def lxml_parse_orderlist_html(self, order_list_html) -> List[Dict]:
        """
        Uses LXML to extract useful info from the HTML of the order list page

            Returns:
                orders (List[Dict]): List or order Dicts
        """
        root = fromstring(order_list_html)
        order_items = root.xpath('//div[@class="order-item"]')
        orders = []
        for order in order_items:
            (order_status,) = order.xpath(
                './/span[@class="order-item-header-status-text"]'
            )
            order_status = order_status.text.lower()
            right_info = order.xpath(
                './/div[@class="order-item-header-right-info"]/div'
            )
            order_date = None
            order_id = None
            for div in right_info:
                info = re.match(
                    (
                        r"^Order (?:date: (?P<order_date>.+)|ID:"
                        r" (?P<order_id>\d+))"
                    ),
                    div.text,
                )
                if info:
                    if info.group("order_date"):
                        order_date = datetime.strptime(
                            info.group("order_date"), "%b %d, %Y"
                        )
                    else:
                        order_id = info.group("order_id")
            if not all([order_date, order_id]):
                self.log.error(
                    (
                        "Unexpected data from order, failed to parse "
                        "order_id %s or order_date (%s)"
                    ),
                    order_id,
                    order_date,
                )
            self.log.debug("Order ID %s har status %s", order_id, order_status)
            (order_total,) = order.xpath(
                './/span[@class="order-item-content-opt-price-total"]'
            )
            info = re.match(r".+\$(?P<dollas>\d+\.\d+)", order_total.text)
            if info:
                order_total = float(info.group("dollas"))
            else:
                order_total = float("0.00")
            (order_store_id,) = order.xpath(
                './/span[@class="order-item-store-name"]/a'
            )
            info = re.match(
                r".+/store/(?P<order_store_id>\d+)", order_store_id.get("href")
            )
            order_store_id = info.group("order_store_id") if info else "0"
            (order_store_name,) = order.xpath(
                './/span[@class="order-item-store-name"]/a/span'
            )
            order_store_name = order_store_name.text
            orders.append(
                {
                    "id": order_id,
                    "status": order_status,
                    "date": order_date,
                    "total": order_total,
                    "store_id": order_store_id,
                    "store_name": order_store_name,
                }
            )
        return orders

    # Methods that use Selenium to scrape webpages in a browser

    def browser_scrape_order_details(self, order: Dict):
        """
        Uses Selenium to visit, load and then save
        the HTML from the order details page of an individual order

        Will also save a copy of item thumbnails and a PDF copy
        of the item's snapshots, since this must be done live.

            Returns:
                order_html (HtmlElement): The HTML from this order['id'] details page
        """
        url = self.ORDER_DETAIL_URL.format(order["id"])
        self.log.info("Visiting %s", url)
        brws = self.browser_visit_page(url, False)

        self.log.info("Waiting for page load")
        time.sleep(3)
        wait10 = WebDriverWait(brws, 10)

        try:
            wait10.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//span[contains(@class, 'switch-icon')]")
                ),
                "Timeout waiting for switch buttons",
            )
            try:
                time.sleep(1)
                # Hide the good damn robot
                god_damn_robot = brws.find_element(By.ID, "J_xiaomi_dialog")
                brws.execute_script(
                    "arguments[0].setAttribute('style', 'display: none;')",
                    god_damn_robot,
                )
            except NoSuchElementException:
                self.log.debug("Fant ingen robot å skjule")
            # Expand address and payment info
            for element in brws.find_elements(
                By.XPATH, "//span[contains(@class, 'switch-icon')]"
            ):
                time.sleep(1)
                WebDriverWait(brws, 30).until_not(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//div[contains(@class, 'comet-loading-wrap')]",
                        )
                    )
                )
                # selenium.common.exceptions.ElementClickInterceptedException:
                # Message: Element
                # <span class="comet-icon comet-icon-arrowdown switch-icon">
                # is not clickable at point (762,405) because another
                # element <div class="comet-loading-wrap"> obscures it
                try:
                    wait10.until(EC.element_to_be_clickable(element)).click()
                    time.sleep(1)
                except ElementClickInterceptedException:
                    try:
                        time.sleep(1)
                        # Hide the good damn robot
                        god_damn_robot = brws.find_element(
                            By.ID, "J_xiaomi_dialog"
                        )
                        brws.execute_script(
                            (
                                "arguments[0].setAttribute('style', 'display:"
                                " none;')"
                            ),
                            god_damn_robot,
                        )
                    except NoSuchElementException:
                        self.log.debug("Fant ingen robot å skjule")
            time.sleep(1)
        except TimeoutException:
            pass

        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        # Save item IDs, thumbnails and PDf snapshots
        if "items" not in order:
            order["items"] = {}
        for item_content in brws.find_elements(
            By.XPATH,
            '//div[contains(@class, "order-detail-item-content-wrap")]',
        ):
            # Retrieve item ID from URL
            thumb = item_content.find_elements(
                By.XPATH,
                './/a[contains(@class, "order-detail-item-content-img")]',
            )[0]
            info = re.match(
                # https://www.aliexpress.com/item/32824370509.html
                r".+item/([0-9]+)\.html.*",
                thumb.get_attribute("href"),
            )
            item_id = info.group(1)
            self.log.debug("Current item id is %s", item_id)

            sku_element = item_content.find_elements(
                By.XPATH, './/div[contains(@class, "item-sku-attr")]'
            )

            # URL and filename-safe base64, so we can
            # reverse the sku to text if we need
            if (
                len(sku_element) == 0
                or len(sku_element[0].text.replace("\xa0", " ").strip()) == 0
            ):
                sku_hash = base64.urlsafe_b64encode(
                    "no-sku".encode("utf-8")
                ).decode("utf-8")
                sku_element = ""
            else:
                sku_element = sku_element[0].text
                sku_hash = base64.urlsafe_b64encode(
                    sku_element.strip().replace("\xa0", " ").encode("utf-8")
                ).decode("utf-8")

            self.log.debug(
                "Sku for item %s is %s, hash %s",
                item_id,
                sku_element.strip().replace("\xa0", " "),
                sku_hash,
            )

            item_sku_id = f"{item_id}-{sku_hash}"
            if not item_sku_id in order["items"]:
                order["items"][item_sku_id] = {}

            # Get snapshot of order page from Ali's archives
            move_mouse = self.browser_save_item_sku_snapshot(
                order, thumb, item_sku_id
            )
            # Thumbnail MUST happen after snapshot, as we hide the snapshot button
            # before saving thumbnail
            self.browser_save_item_thumbnail(
                order, thumb, item_sku_id, move_mouse
            )

        return fromstring(brws.page_source)

    def browser_save_item_thumbnail(
        self, order, thumb, item_sku_id, move_mouse=False
    ):
        # Find and hide the snapshot "camera" graphic that
        # overlays the thumbnail
        snapshot_parent = thumb.find_element(
            By.XPATH, './/div[@class="order-detail-item-snapshot"]'
        )
        self.browser.execute_script(
            "arguments[0].setAttribute('style', 'display: none;')",
            snapshot_parent,
        )

        # move the "mouse" off the element so we do not get
        # a floating text box
        # random = thumb.find_element(By.XPATH, './/parent::*')
        # If we try to move the mouse without having "clicked" on
        # anything on "this" page, selenium gets a brain aneurysm
        if move_mouse:
            ActionChains(self.browser).move_to_element_with_offset(
                thumb, 130, 0
            ).perform()

        # Save copy of item thumbnail (without snapshot that
        # would appear if we screenshot the element)
        # This is 100000x easier than extracting the actual
        # image via some js trickery
        thumb_data = thumb.screenshot_as_base64
        order["items"][item_sku_id]["thumbnail"] = (
            self.THUMB_FILENAME_TEMPLATE.format(
                order_id=order["id"], item_id=item_sku_id
            )
        )
        self.write(
            order["items"][item_sku_id]["thumbnail"],
            base64.b64decode(thumb_data),
            binary=True,
        )

    def browser_save_item_sku_snapshot(self, order, thumb, item_sku_id):
        """
        Uses Selenium to save the AliExpress snapshot of the
        current item id+item sku to PDF.
        """
        if "snapshot" not in order["items"][item_sku_id]:
            order["items"][item_sku_id]["snapshot"] = {
                "pdf": self.SNAPSHOT_FILENAME_TEMPLATE.format(
                    order_id=order["id"], item_id=item_sku_id, ext="pdf"
                ),
                "html": self.SNAPSHOT_FILENAME_TEMPLATE.format(
                    order_id=order["id"], item_id=item_sku_id, ext="html"
                ),
            }
        if self.can_read(
            order["items"][item_sku_id]["snapshot"]["pdf"]
        ) and self.can_read(order["items"][item_sku_id]["snapshot"]["html"]):
            self.log.info(
                "Not opening snapshot, already saved: %s", item_sku_id
            )
            return False
        order_details_page_handle = self.browser.current_window_handle
        self.log.debug(
            "Order details page handle is %s", order_details_page_handle
        )
        snapshot = thumb.find_element(
            By.XPATH,
            #'.//div[contains(@class, "order-detail-item-snapshot")]//*[local-name()="svg"]'
            './/div[contains(@class, "order-detail-item-snapshot")]',
        )
        snapshot.click()
        # Sleep for a while so the tabs get their proper URL
        time.sleep(5)
        self.log.debug("Window handles: %s", self.browser.window_handles)
        debug_found_snapshot = False
        for handle in self.browser.window_handles:
            self.log.debug(
                "Looking for snapshot tab of %s, current handle: %s",
                item_sku_id,
                handle,
            )
            if handle == order_details_page_handle:
                self.log.debug("Found order details page, skipping: %s", handle)
                continue
            self.browser.switch_to.window(handle)
            if "snapshot" in self.browser.current_url:
                self.log.debug("Found snapshot tab")
                self.browser_cleanup_item_page()
                time.sleep(2)
                self.remove(self.cache["PDF_TEMP_FILENAME"])

                self.log.debug("Trying to print to PDF")
                self.browser.execute_script("window.print();")
                # Do some read- and size change tests
                # to try to detect when printing is complete
                while not self.can_read(self.cache["PDF_TEMP_FILENAME"]):
                    self.log.debug("PDF file does not exist yet")
                    time.sleep(1)
                self.wait_for_stable_file(self.cache["PDF_TEMP_FILENAME"])
                self.move_file(
                    self.cache["PDF_TEMP_FILENAME"],
                    order["items"][item_sku_id]["snapshot"]["pdf"],
                )
                self.write(
                    order["items"][item_sku_id]["snapshot"]["html"],
                    self.browser.page_source,
                    html=True,
                )
                debug_found_snapshot = True
            else:
                self.log.debug(
                    "Found random page, closing: %s with url %s",
                    handle,
                    self.browser.current_url,
                )
            self.browser.close()
        if not debug_found_snapshot:
            self.log.debug(
                RED(
                    "Failed to find snapshot, sleeping 100000 seconds for debug"
                )
            )
            time.sleep(100000)
        self.log.debug("Switching to order details page")
        self.browser.switch_to.window(order_details_page_handle)
        return True

    def browser_cleanup_item_page(self) -> None:
        brws = self.browser
        self.log.debug("Hide fluff, ads, etc")
        elemets_to_hide: List[WebElement] = []
        for element_xpath in []:
            elemets_to_hide += brws.find_elements(By.XPATH, element_xpath)

        for element_id in []:
            elemets_to_hide += brws.find_elements(By.ID, element_id)

        for css_selector in [
            "div.site-footer",
            "div.footer-copywrite",
            "#top-lighthouse",
            "#header",
            "#view-product",
        ]:
            elemets_to_hide += brws.find_elements(By.CSS_SELECTOR, css_selector)

        for element in []:
            elemets_to_hide += brws.find_elements(element[0], element[1])

        page = brws.find_element(By.ID, "page")
        preview_images: List[WebElement] = brws.find_elements(
            By.CSS_SELECTOR, "li.image-nav-item img"
        )

        brws.execute_script(
            """
                // remove spam/ad elements
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].remove()
                }
                // Give page rooooooom
                arguments[1].style.width="100%"
                // preview_images
                for (let i = 0; i < arguments[2].length; i++) {
                    var img = document.createElement('img');
                    img.src = arguments[2][i].src;
                    console.log(img.src)
                    arguments[3].appendChild(img); // #product-desc
                }
                style = document.createElement('style');
                style.innerHTML = "@page {size: A4 portrait;}";
                document.head.appendChild(style);
                """,
            elemets_to_hide,
            page,
            preview_images,
            brws.find_element(By.CSS_SELECTOR, "#product-desc"),
        )
        time.sleep(2)
        self.log.debug("Set max-width of all images")
        all_images = brws.find_elements(By.TAG_NAME, "img")
        brws.execute_script(
            """
                // set max-width of images
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].style.maxWidth = "900px"
                }
                """,
            all_images,
        )

    def get_scrape_tracking_page_html(self, order: Dict):
        """
        Uses LXML to read from cache, or Selenium to visit, load
        and then save the HTML from the tracking page of an individual order

            Returns:
                tracking_html (HtmlElement): The HTML from this order['id'] tracking page
        """
        order["tracking_cache_file"] = (
            self.TRACKING_HTML_FILENAME_TEMPLATE.format(order_id=order["id"])
        )
        if os.access(order["tracking_cache_file"], os.R_OK):
            with open(
                order["tracking_cache_file"], "r", encoding="utf-8"
            ) as ali_ordre:
                self.log.debug(
                    "Loading individual order tracking data cache: %s",
                    order["tracking_cache_file"],
                )
                return fromstring(ali_ordre.read())
        self.browser_visit_page(
            self.ORDER_TRACKING_URL.format(order["id"]), False
        )
        time.sleep(1)
        self.browser.execute_script(
            "window.scrollTo(0,document.body.scrollHeight)"
        )
        self.log.debug("Waiting 10 seconds for tracking page load")
        try:
            self.browser.find_element(
                By.XPATH, "//div[contains(@class, 'benifit-cancel')]"
            ).click()
            self.log.debug("Hiding message about shipping benefits")
        except NoSuchElementException:
            pass

        self.browser.execute_script(
            "window.scrollTo(0,document.body.scrollHeight)"
        )
        time.sleep(10)

        with open(
            order["tracking_cache_file"], "w", encoding="utf-8"
        ) as ali_ordre:
            tracking_html = fromstring(self.browser.page_source)
            ali_ordre.write(tostring(tracking_html).decode("utf-8"))
        return tracking_html

    def browser_scrape_order_list_html(self):
        """
        Uses Selenium to visit, load, save and then
        return the HTML from the order list page

            Returns:
                order_list_html (str): The HTML from the order list page
        """
        brws = self.browser_visit_page(self.ORDER_LIST_URL, False)
        wait10 = WebDriverWait(brws, 10)
        # Find and click the tab for completed orders
        try:
            wait10.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        (
                            "//div[@class='comet-tabs-nav-item']"
                            "[contains(text(), 'Completed')]"
                        ),
                    )
                )
            ).click()
        except ElementClickInterceptedException:
            # Apparently så var ikke sjekken over atomisk, så
            # vi venter litt til før vi klikker
            time.sleep(5)
            wait10.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        (
                            "//div[@class='comet-tabs-nav-item']"
                            "[contains(text(), 'Completed')]"
                        ),
                    )
                )
            ).click()

        # Wait until the tab for completed orders are complete
        wait10.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    (
                        "//div[contains(@class, 'comet-tabs-nav-item') and "
                        "contains(@class, 'comet-tabs-nav-item-active')]"
                        "[contains(text(), 'Completed')]"
                    ),
                )
            )
        )
        time.sleep(5)
        self.log.debug("Loading order page")
        while True:
            try:
                # Hide the good damn robot
                god_damn_robot = brws.find_element(By.ID, "J_xiaomi_dialog")
                brws.execute_script(
                    "arguments[0].setAttribute('style', 'display: none;')",
                    god_damn_robot,
                )
            except NoSuchElementException:
                pass
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(3)
            try:
                element = wait10.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            (
                                "//button[contains(@class, 'comet-btn')]"
                                "/span[contains(text(), 'View orders')]"
                                "/parent::button"
                            ),
                        )
                    ),
                    "Timeout waiting for View orders button",
                )
                element.click()
            except StaleElementReferenceException:
                brws.execute_script(
                    "window.scrollTo(0,document.body.scrollHeight)"
                )
                time.sleep(3)
                continue
            except TimeoutException:
                break
        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        self.log.info("All completed orders loaded (hopefully)")
        with open(self.ORDER_LIST_FILENAME, "w", encoding="utf-8") as ali:
            html = fromstring(brws.page_source)
            ali.write(tostring(html).decode("utf-8"))
        return brws.page_source

    # Browser util methods
    def browser_login(self, expected_url):
        """
        Uses Selenium to log in AliExpress.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required.
        """
        self.log.info(AMBER("We need to log in to Aliexpress"))

        url_re_escaped = re.escape(expected_url)
        order_list_url_re_espaced = re.escape(self.ORDER_LIST_URL)
        brws, username_data, password_data = self.browser_setup_login_values()
        if username_data and password_data:
            # We go to the order list, else ... maybe russian?
            brws.get(self.ORDER_LIST_URL)

            wait = WebDriverWait(brws, 10)
            try:
                username = wait.until(
                    EC.presence_of_element_located((By.ID, "fm-login-id"))
                )
                password = wait.until(
                    EC.presence_of_element_located((By.ID, "fm-login-password"))
                )
                username.send_keys(username_data)
                password.send_keys(password_data)
                wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@type='submit'][not(@disabled)]")
                    )
                ).click()
                order_list_page = False
                try:
                    WebDriverWait(brws, 15).until(
                        EC.url_matches(order_list_url_re_espaced)
                    )
                    order_list_page = True
                except TimeoutException:
                    pass
                if not order_list_page:
                    brws.execute_script(
                        "alert('Please complete login (CAPTCHA etc.). You have"
                        " two minutes.');"
                    )
                    self.log.warning(
                        "Please complete log in to Aliexpress in the browser"
                        " window.."
                    )
                    WebDriverWait(brws, 30).until_not(
                        EC.alert_is_present(),
                        "Please close alert an continue login!",
                    )
                    self.log.info(
                        "Waiting up to 120 seconds for %s",
                        order_list_url_re_espaced,
                    )
                    WebDriverWait(brws, 120).until(
                        EC.url_matches(order_list_url_re_espaced)
                    )
            except TimeoutException:
                try:
                    brws.switch_to.alert.accept()
                except NoAlertPresentException:
                    pass
                self.browser_safe_quit()
                # pylint: disable=raise-missing-from
                raise RuntimeError("Login to Aliexpress was not successful.")
        brws.get(expected_url)
        self.log.info("Waiting up to 120 seconds for %s", url_re_escaped)
        WebDriverWait(brws, 120).until(EC.url_matches(url_re_escaped))

    # Command functions, used in scrape.py

    def command_scrape(self):
        """
        Scrapes your AliExpress orders, logging you in using
        an automated browser if required.
        """
        try:
            order_list_html = self.load_order_list_html()
            orders = self.lxml_parse_orderlist_html(order_list_html)
            self.get_individual_order_details(orders)
        except NoSuchWindowException:
            self.log.error(
                RED(
                    "Login to Aliexpress was not successful. "
                    "Please do not close the browser window."
                )
            )
        self.browser_safe_quit()

    # Class init

    def __init__(self, options: Dict):
        super().__init__(options, __name__)
        super().setup_cache(Path("aliexpress"))
        self.setup_templates()

    def part_to_filename(self, _, **__):
        # Not used here yet
        return None
