import base64
import datetime
import math
import os
import re
import time
import urllib.request
import argparse
from pathlib import Path
from typing import Dict, Final, List
from urllib.parse import urlparse

from lxml.html import HtmlElement
from lxml.html.soupparser import fromstring
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from . import settings
from .base import BaseScraper, PagePart

# pylint: disable=unused-import
from .utils import RED, BLUE, GREEN, AMBER


class AmazonScraper(BaseScraper):
    TLD: Final[str] = "test"
    YEARS: Final[List]
    # Xpath to individual order item parent element
    ORDER_CARD_XPATH: Final[str] = "//div[contains(@class, 'js-order-card')]"

    def command_to_std_json(self):
        raise NotImplementedError("Std export not implemented")

    # Scraper commands and __init__
    def command_scrape(self) -> None:
        order_lists_html = self.load_order_lists_html()
        order_lists = self.lxml_parse_order_lists_html(order_lists_html)
        self.save_order_lists_to_json(order_lists)
        order_lists = self.load_order_lists_from_json()

        if settings.AMZ_ORDERS_SKIP:
            self.log.debug(
                "Skipping scraping order IDs: %s",
                settings.AMZ_ORDERS_SKIP,
            )
        if self.AMZ_ORDERS:
            self.log.debug("Scraping only order IDs: %s", self.AMZ_ORDERS)
        count = 0
        for year in self.YEARS:
            # self.log.debug("Year: %s", year)
            for order_id in order_lists[year]:
                if self.skip_order(order_id, count):
                    continue
                count += 1
                self.parse_order(order_id, order_lists[year][order_id])
                # self.pprint({ order_id: order_lists[year][order_id]})
                # Write order to json here?
        # self.pprint(order_lists)
        self.browser_safe_quit()

    def __init__(self, options: argparse.Namespace):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        self.DO_CACHE_ORDERLIST = options.use_cached_orderlist
        self.TLD = self.check_tld(options.tld)
        self.LOGIN_PAGE_RE = rf"^https://www\.amazon\.{self.TLD}/ap/signin"
        self.AMZ_ORDERS = (
            settings.AMZ_ORDERS[self.TLD]
            if self.TLD in settings.AMZ_ORDERS
            else []
        )

        super().setup_cache(Path(f'amazon_{self.TLD.replace(".","_")}'))
        self.YEARS = self.check_year(
            options.year, options.start_year, options.not_archived
        )
        self.setup_templates()
        self.name = f"amazon.{options.tld}"
        self.tla = "AMZ"

    def load_order_lists_from_json(self):
        order_lists = {}
        for year in self.YEARS:
            order_lists[year] = self.read_json(
                PagePart.ORDER_LIST_JSON, year=year
            )
        return order_lists

    def parse_order(self, order_id: str, order_id_dict: Dict):
        order_json_filename = self.part_to_filename(
            PagePart.ORDER_DETAILS, order_id=order_id, ext="json"
        )
        if self.can_read(order_json_filename):
            # TODO: Enable order loading from json when ready
            if False is True:
                order_id_dict.update(
                    self.read(order_json_filename, from_json=True)
                )

        order_cache_dir = self.cache["ORDERS"] / Path(order_id)
        html_cache = Path(
            self.part_to_filename(
                PagePart.ORDER_DETAILS, order_id=order_id, ext="html"
            )
        )

        self.makedir(order_cache_dir)

        if not self.can_read(html_cache):
            self.log.debug("Did not find HTML cache for order %s", order_id)
            order_id_dict.update(
                self.browser_scrape_order(order_id, order_cache_dir)
            )

        self.log.debug("Found HTML cache for order %s", order_id)
        order_id_dict = self.lxml_scrape_order(
            order_id, html_cache, order_cache_dir, order_id_dict
        )

        # self.pprint(order_id_dict)
        self.pprint({order_id: order_id_dict})

    def lxml_scrape_order(
        self,
        order_id,
        html_cache_filename: Path,
        order_cache_dir: Path,
        order_id_dict: Dict,
    ):
        # TODO: Scrape order with LXML

        attachements = order_cache_dir.glob("attachement-*.pdf")
        for attachement in attachements:
            if "attachements" not in order_id_dict:
                order_id_dict["attachements"] = []

            m = re.match(r"attachement-(.*)\.pdf", attachement.name)

            order_id_dict["attachements"].append(
                {
                    "name": base64.urlsafe_b64decode(m[1]).decode("utf-8"),
                    "path": str(attachement.relative_to(self.cache["BASE"])),
                }
            )

        order_html = self.read(html_cache_filename, from_html=True)
        a: HtmlElement = order_html.cssselect(".a-fixed-right-grid")[0]
        b: HtmlElement = a.cssselect("#od-subtotals")[0]
        price_rows: HtmlElement = b.cssselect(".a-row")
        order_id_dict["pricing"] = {}
        # del order_id_dict["total"]
        for price_row in price_rows:
            price_columns: List[HtmlElement] = price_row.xpath(".//div")
            if len(price_columns) == 2:
                price_name = price_columns[0].text_content().strip()
                order_id_dict["pricing"][price_name] = self.get_value_currency(
                    price_name, price_columns[1].text_content().strip()
                )
            # self.log.debug("".join(price_row.itertext()))
        # .a-fixed-right-grid
        #    .od-shipping-address-container
        #    #od-subtotals

        # item_files = order_cache_dir.glob("item-*")

        if "total" in order_id_dict and not isinstance(
            order_id_dict["total"], dict
        ):
            order_id_dict["total"] = self.get_value_currency(
                "total", order_id_dict["total"]
            )
        return order_id_dict

    def append_thumnails_to_item_html(self):
        brws = self.browser
        self.log.debug("View and preload all item images")

        img_btns = brws.find_elements(
            By.XPATH, "//li[contains(@class,'imageThumbnail')]"
        )

        # This will add the attribute data-old-hires for
        # those images that have high-res versions
        for img_btn in img_btns:
            time.sleep(1)
            img_btn.click()
        if len(img_btns):
            img_btns[0].click()

        img_urls = []
        for image in brws.find_elements(
            By.CSS_SELECTOR,
            "li.image.item div.imgTagWrapper img",
        ):
            image_src = image.get_attribute("data-old-hires")
            if image_src:
                large_image_src = image_src
            else:
                image_src = image.get_attribute("src")
                # No highres, get as big a image as possible
                # Remove all resize etc, leave ayto crop
                large_image_src = re.sub(
                    r"(.+\._)[^\.]*(_\.+)", r"\1AC\2", image_src
                )
            # print("Small:", image_src)
            # print("Large: ", large_image_src)
            img_urls.append(large_image_src)

        self.log.debug("Include all item images on bottom of page")
        image_main: WebElement
        try:
            image_main = brws.find_element(By.ID, "imgBlkFront")
        except NoSuchElementException:
            image_main = brws.find_element(By.ID, "landingImage")
        expanded_content = []
        try:
            expanded_content += brws.find_elements(
                By.CSS_SELECTOR, ".a-expander-content"
            )
        except NoSuchElementException:
            self.log.debug("No expanded content found")
            # pass
        try:
            expanded_content += brws.find_elements(
                By.CSS_SELECTOR, ".a-expander-partial-collapse-container"
            )
        except NoSuchElementException:
            self.log.debug("No expanded content found")
            # pass

        self.browser.execute_script(
            """
                for (let i = 0; i < arguments[0].length; i++) {
                    var img = document.createElement('img');
                    img.src = arguments[0][i];
                    arguments[1].appendChild(img);
                    console.log("Appending " + img)
                }
                // Removeing these somehow stops main image
                // from overflowing the text in PDF
                arguments[2].style.removeProperty("max-height") 
                arguments[2].style.removeProperty("max-width")

                console.log("expanded_content")
                console.log(arguments[3])
                for (let i = 0; i < arguments[3].length; i++) {
                    arguments[3][i].style.position = "static"
                }
                """,
            img_urls,
            brws.find_element(By.ID, "dp"),
            image_main,
            expanded_content,
        )
        time.sleep(1)

    def save_order_attachements(self, order_cache_dir, attachement_dict):
        brws = self.browser
        wait2 = WebDriverWait(brws, 2)
        order_handle = brws.current_window_handle
        invoice_a_xpath = (
            "//a[contains(@class, 'a-popover-trigger')]"
            "/span[contains(text(), 'Invoice')]/ancestor::a"
        )
        order_summary_a_xpath = (
            "//span[contains(@class, 'a-button')]//a[contains(@href,"
            " 'summary/print.html')]"
        )

        invoice_wrapper_div_xpath = (
            "//div[contains(@class, 'a-popover-wrapper')]"
        )
        # Need to wait a tiny bit for the JS
        # connected to this link to load
        time.sleep(2)
        elements_to_loop: List[WebElement] = None
        try:
            elements_to_loop: List[WebElement] = [
                brws.find_element(By.XPATH, order_summary_a_xpath)
            ]
        except NoSuchElementException:
            pass
        if not elements_to_loop:
            try:
                wait2.until(
                    EC.presence_of_element_located((By.XPATH, invoice_a_xpath)),
                    "Timeout waiting for Invoice",
                ).click()
                self.log.debug("Found Invoice button")
                time.sleep(1)
                # then this should appear
                invoice_wrapper: WebElement = wait2.until(
                    EC.presence_of_element_located(
                        (By.XPATH, invoice_wrapper_div_xpath)
                    ),
                    "Timeout waiting for invoice wrapper",
                )
                elements_to_loop: List[WebElement] = (
                    invoice_wrapper.find_elements(By.TAG_NAME, "a")
                )
            except (TimeoutException, NoSuchElementException):
                pass
        if not elements_to_loop:
            self.log.debug(
                "We found no order summary, invoices or other attachementes to"
                " save. This is possibly a bug."
            )
            raise RuntimeError(
                "We found no order summary, invoices or other attachementes to"
                " save. This is possibly a bug."
            )

        self.log.debug("Looping and possibly downloading attachements")

        for invoice_item in elements_to_loop:
            text = (
                invoice_item.text.replace("\r\n", " ")
                .replace("\r", "")
                .replace("\n", " ")
            )
            self.log.debug("Found attachement with name '%s'", text)
            href = invoice_item.get_attribute("href")
            attachement = {"text": text, "href": href}

            text_filename_safe = base64.urlsafe_b64encode(
                text.encode("utf-8")
            ).decode("utf-8")

            attachement_file = (
                order_cache_dir / Path(f"attachement-{text_filename_safe}.pdf")
            ).resolve()

            if self.can_read(attachement_file):
                attachement["file"] = str(
                    attachement_file.relative_to(self.cache["BASE"])
                )
                attachement_dict.append(attachement)
                self.log.debug("We already have the file for '%s' saved", text)
                continue

            order_summary = re.match(
                r".+(summary/print|order-summary\.html.+print).+", href
            )
            download_pdf = re.match(
                r".+(/download/.+\.pdf|generated_invoices.+\.pdf.+)", href
            )
            contact_link = re.match(r".+contact/contact.+", href)
            invoice_unavailable = re.match(r".+legal_invoice_help.+", href)
            if order_summary:
                self.remove(self.cache["PDF_TEMP_FILENAME"])
                brws.switch_to.new_window("tab")
                brws.get(href)
                self.log.debug("Found order summary.")
                self.browser.execute_script("window.print();")
                self.wait_for_stable_file(self.cache["PDF_TEMP_FILENAME"])
                attachement["file"] = str(
                    Path(attachement_file).relative_to(self.cache["BASE"])
                )  # keep this
                self.move_file(
                    self.cache["PDF_TEMP_FILENAME"], attachement_file
                )
                brws.close()
            elif download_pdf:
                self.log.debug("This is a invoice/warranty/p-slip PDF.")
                for pdf in self.cache["TEMP"].glob("*.pdf"):
                    # Remove old/random PDFs
                    os.remove(pdf)
                self.log.debug(
                    "Opening PDF, waiting for it to download in background"
                )
                brws.switch_to.new_window()
                # Can't use .get(...) here, since Selenium appears to
                # be confused by the fact that Firefox downloads the PDF
                brws.execute_script(
                    """
                    setTimeout(() => {
                        document.location.href = arguments[0];
                    }, "500");
                    """,
                    href,
                )
                ## Look for PDF in folder
                pdf = list(self.cache["TEMP"].glob("*.pdf"))
                while not pdf:
                    pdf = list(self.cache["TEMP"].glob("*.pdf"))
                    time.sleep(3)
                # We have a PDF, move it to  a proper name
                self.wait_for_stable_file(pdf[0])
                attachement["file"] = str(
                    Path(attachement_file).relative_to(self.cache["BASE"])
                )  # keep this
                self.move_file(pdf[0], attachement_file)
                brws.close()
            elif contact_link or invoice_unavailable:
                self.log.warning(
                    "Contact or lnvoice unavailable link, nothing useful to"
                    " save"
                )
            else:
                self.log.warning(
                    AMBER("Unknown attachement, not saving: %s, %s"),
                    text,
                    href,
                )
            attachement_dict.append(attachement)
            brws.switch_to.window(order_handle)
        return invoice_a_xpath, order_summary_a_xpath, invoice_wrapper_div_xpath

    def lxml_parse_order_lists_html(self, order_lists_html: Dict) -> None:
        order_lists = {}
        if order_lists_html:
            for key in order_lists_html:
                html = order_lists_html[key]
                year, _ = key
                order_card = html.xpath(self.ORDER_CARD_XPATH)
                # There are not items on this page
                if len(order_card) == 0:
                    order_lists[year] = {}
                    self.log.info(
                        "%s has no orders, returning empty dict", year
                    )
                else:
                    if year not in order_lists:
                        order_lists[year] = {}
                    for order_card in order_card:
                        values = order_card.xpath(
                            ".//span[contains(@class, 'value')]"
                        )

                        value_matches = {
                            "date": None,
                            "id": None,
                            "total": None,
                        }
                        for value in values:
                            txtvalue = "".join(value.itertext()).strip()
                            matches = re.match(
                                r"(?P<date1>^\d+ .+ \d\d\d\d$)|"
                                r"(?P<date2>.+ \d+, \d\d\d\d$)|"
                                r"(?P<id>[0-9D]\d\d-.+)|"
                                r"(?P<total>.*\d+(,|\.)\d+.*)",
                                txtvalue,
                            )
                            if not matches:
                                raise RuntimeError(
                                    f"We failed to match '{txtvalue}' "
                                    "to one of id/date/total"
                                )

                            matches_dict = matches.groupdict().copy()
                            if matches.group("date1"):
                                matches_dict["date"] = (
                                    datetime.datetime.strptime(
                                        matches.group("date1"), "%d %B %Y"
                                    )
                                )

                            elif matches.group("date2"):
                                matches_dict["date"] = (
                                    datetime.datetime.strptime(
                                        matches.group("date2"), "%B %d, %Y"
                                    )
                                )

                            del matches_dict["date1"]
                            del matches_dict["date2"]

                            value_matches.update(
                                {k: v for (k, v) in matches_dict.items() if v}
                            )

                        if value_matches["id"] not in order_lists[year]:
                            order_lists[year][value_matches["id"]] = {
                                "items": {}
                            }

                        order_lists[year][value_matches["id"]]["total"] = (
                            value_matches["total"]
                        )

                        order_lists[year][value_matches["id"]]["date"] = (
                            value_matches["date"]
                        )
                        self.log.info(
                            "Order ID %s, %s, %s",
                            value_matches["id"],
                            value_matches["total"],
                            value_matches["date"].strftime("%Y-%m-%d"),
                        )
        else:
            self.log.debug("No order HTML to parse")
        return order_lists

    def save_order_list_cache_html_file(self, year, start_index):
        json_file = self.part_to_filename(PagePart.ORDER_LIST_JSON, year=year)
        # If we are saving a new HTML cache, invalidate possible json
        if self.remove(json_file):
            self.log.debug("Removed json cache for %s", year)
        cache_file = self.part_to_filename(
            PagePart.ORDER_LIST_HTML, year=year, start_index=start_index
        )
        self.log.info(
            "Saving cache to %s and appending to html list", cache_file
        )
        self.rand_sleep()
        return self.write(cache_file, self.browser.page_source, html=True)

    def load_order_lists_html(self) -> Dict[int, str]:  # FIN
        """
        Returns the order list html, eithter from disk
        cache or using Selenium to visit the url.

            Returns:
                order_list_html (List[str]): A list of the HTML from the order list pages
        """
        order_list_html = {}
        missing_years = []
        self.log.debug("Looking for %s", ", ".join(str(x) for x in self.YEARS))
        missing_years = self.YEARS.copy()
        json_cache = []
        if self.DO_CACHE_ORDERLIST:
            self.log.debug("Checking orderlist caches")
            for year in self.YEARS:
                self.log.debug(
                    "Looking for cache of %s", str(year).capitalize()
                )
                found_year = False
                if self.has_json(PagePart.ORDER_LIST_JSON, year=year):
                    self.log.debug(
                        "%s already has json", str(year).capitalize()
                    )
                    json_cache.append(year)
                    found_year = True
                else:
                    start_index = 0
                    more_pages_this_year = True
                    while more_pages_this_year:
                        html_filename = self.part_to_filename(
                            PagePart.ORDER_LIST_HTML,
                            year=year,
                            start_index=start_index,
                        )
                        self.log.debug(
                            "Looking for cache in: %s", html_filename
                        )
                        if self.can_read(html_filename):
                            found_year = True
                            self.log.debug(
                                "Found cache for %s, index %s",
                                year,
                                start_index,
                            )
                            order_list_html[(year, start_index)] = fromstring(
                                self.read(html_filename)
                            )
                            start_index += 10
                        else:
                            more_pages_this_year = False

                if found_year:
                    missing_years.remove(year)

        self.log.debug(
            "Found HTML cache for order list: %s",
            ", ".join([str(x) for x in self.YEARS if x not in missing_years]),
        )
        self.log.debug(
            "Found JSON cache for order list: %s",
            ", ".join([str(x) for x in json_cache]),
        )
        if missing_years:
            self.log.info(
                "Missing HTML cache for: %s",
                ", ".join(str(x) for x in missing_years),
            )
            order_list_html.update(
                self.browser_scrape_order_lists(missing_years)
            )
        return order_list_html

    def save_order_lists_to_json(self, order_lists: Dict) -> None:
        for year in order_lists:
            json_filename = self.part_to_filename(
                PagePart.ORDER_LIST_JSON, year=year
            )
            self.write(json_filename, order_lists[year], to_json=True)
            self.log.debug("Saved order list %s to JSON", year)

    # Function primarily using Selenium to scrape websites
    def browser_scrape_order_lists(self, years: List):
        """
        Uses Selenium to visit, load, save and then
        return the HTML from the order list page

            Returns:
                order_lists_html (Dict[str]): A list of the HTML from the order list pages
        """
        self.log.debug(
            "Scraping %s using Selenium", ", ".join(str(x) for x in years)
        )
        order_list_html = {}
        for year in years:
            more_pages = True
            start_index = 0
            while more_pages:
                more_pages = self.browser_scrape_individual_order_list_page(
                    year, start_index, order_list_html
                )
                start_index += 10
                self.rand_sleep()
        return order_list_html

    def browser_login(self, _):
        """
        Uses Selenium to log in
        """
        brws, username_data, password_data = self.browser_setup_login_values()
        if username_data and password_data:
            self.log.info(
                AMBER("We need to log in to amazon.%s"),
                self.TLD,
            )
            brws = self.browser_get_instance()

            wait = WebDriverWait(brws, 10)
            try:
                self.rand_sleep()
                username = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_email"))
                )
                username.send_keys(username_data)
                self.rand_sleep()
                wait.until(
                    EC.element_to_be_clickable(((By.ID, "continue")))
                ).click()
                self.rand_sleep()
                password = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_password"))
                )
                password.send_keys(password_data)
                self.rand_sleep()
                remember = wait.until(
                    EC.presence_of_element_located((By.NAME, "rememberMe"))
                )
                remember.click()
                self.rand_sleep()
                sign_in = wait.until(
                    EC.presence_of_element_located(
                        (By.ID, "auth-signin-button")
                    )
                )
                sign_in.click()
                self.rand_sleep()

            except TimeoutException as tee:
                self.browser_safe_quit()
                self.log.error(
                    RED(
                        "Login to Amazon was not successful "
                        "because we could not find a expected element.."
                    )
                )
                raise tee
        if (
            re.match(self.LOGIN_PAGE_RE, self.browser.current_url)
            or "transactionapproval" in self.browser.current_url
        ):
            self.log.error("Login to Amazon was not successful.")
            self.log.error(
                RED(
                    "If you want to continue please complete log (CAPTCHA/2FA),"
                    " and then press enter."
                )
            )
            input()
            if (
                re.match(self.LOGIN_PAGE_RE, self.browser.current_url)
                or "transactionapproval" in self.browser.current_url
            ):
                self.log.error(
                    RED(
                        "Login to Amazon was not successful, even after user"
                        " interaction."
                    )
                )
                raise RuntimeError()
        self.log.info(GREEN("Login to Amazon was successful."))

    def browser_scrape_order(
        self, order_id: str, order_cache_dir: Path
    ) -> Dict:
        order = {}
        curr_url = self.ORDER_URL_TEMPLATE.format(order_id=order_id)
        self.log.debug("Scraping %s, visiting %s", order_id, curr_url)
        brws = self.browser_visit_page(curr_url, goto_url_after_login=True)
        wait2 = WebDriverWait(brws, 2)

        order["attachements"] = []
        order_handle = brws.current_window_handle
        invoice_a_xpath, order_summary_a_xpath, invoice_wrapper_div_xpath = (
            self.save_order_attachements(order_cache_dir, order["attachements"])
        )

        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        time.sleep(2)

        if "items" not in order:
            order["items"] = {}

        self.log.debug("Scraping item IDs and thumbnails")

        for item in brws.find_elements(
            By.XPATH, "//div[contains(@class, 'yohtmlc-item')]/parent::div"
        ):
            item_id = None
            for atag in item.find_elements(By.TAG_NAME, "a"):
                product_link = re.match(
                    # item id or "gc" => gift card
                    r".+/product/(?P<id>([A-Z0-9]*|gc)).+",
                    atag.get_attribute("href"),
                )
                if product_link:
                    item_id = product_link.group("id")
            self.log.debug("Item id: %s", item_id)
            assert item_id
            if item_id not in order["items"]:
                order["items"][item_id] = {}

            # Don't save anything for gift cards
            if item_id != "gc":
                thumb = item.find_element(
                    By.XPATH, ".//img[contains(@class, 'yo-critical-feature')]"
                )
                high_res_thumb_url = thumb.get_attribute("data-a-hires")
                # _AC_UY300_SX300_
                # 1. Autocrop
                # 2. Resize Y to 300px
                # 3. Scale X so no larger than 300px
                large_image_src = re.sub(
                    r"(.+\._)[^\.]*(_\.+)",
                    r"\1AC_UY300_SX300\2",
                    high_res_thumb_url,
                )
                ext = os.path.splitext(urlparse(large_image_src).path)[1]
                item_thumb_file = (
                    order_cache_dir / Path(f"item-{item_id}-thumb{ext}")
                ).resolve()

                urllib.request.urlretrieve(large_image_src, item_thumb_file)
                order["items"][item_id]["thumbnail"] = str(
                    Path(item_thumb_file).relative_to(self.cache["BASE"])
                )  # keep this

        self.log.debug("Saving item pages to PDF and HTML")
        for item_id in order["items"]:
            self.browser_scrape_item_page(
                item_id, order["items"][item_id], order_id, order_cache_dir
            )
            brws.switch_to.window(order_handle)

        time.sleep(10)
        self.log.debug("Opening order page again")
        brws.switch_to.window(order_handle)

        # We "open" the Invoice popup before saving HTML
        # so it is in the DOM
        try:
            brws.find_element(By.XPATH, order_summary_a_xpath)
            # If we found this, there is not Invoice link
        except NoSuchElementException:
            # We should expect to find a invoice link or wrapper
            try:
                brws.find_element(By.XPATH, invoice_wrapper_div_xpath)
            except NoSuchElementException:
                # Invoice wrapper is not open, need to open it
                try:
                    wait2.until(
                        EC.presence_of_element_located(
                            (By.XPATH, invoice_a_xpath)
                        ),
                        "Timeout waiting for Invoice button",
                    ).click()
                    wait2.until(
                        EC.presence_of_element_located(
                            (By.XPATH, invoice_wrapper_div_xpath)
                        ),
                        "Timeout waiting for Invoice popup",
                    )
                except TimeoutException:
                    # pylint: disable=raise-missing-from
                    raise RuntimeError(
                        "Invoice popup did not open as expected, or did not"
                        " find invoice link. We need this open to save it to"
                        " HTML cache."
                    )
        self.write(
            self.part_to_filename(
                PagePart.ORDER_DETAILS, order_id=order_id, ext="html"
            ),
            brws.page_source,
            html=True,
        )
        self.log.debug("Saved order page HTML to file")
        return order

    def browser_scrape_item_page(
        self,
        item_id: str,
        item_dict: Dict,
        order_id: str,
        order_cache_dir: Path,
    ):
        # TODO: Finish process_item_page
        brws = self.browser
        self.log.debug("New tab for item %s", item_id)
        brws.switch_to.new_window()
        brws.get(self.ITEM_URL_TEMPLATE.format(item_id=item_id))
        item_dict["removed"] = False

        if "Page Not Found" not in self.browser.title:
            self.log.debug("Slowly scrolling to bottom of item page")
            brws.execute_script(
                """
                var hlo_wh = window.innerHeight/2;
                var hlo_count = 0;
                var intervalID = setInterval(function() {
                    window.scrollTo(0,hlo_wh*hlo_count)
                    hlo_count = hlo_count + 1;
                    console.log(hlo_count)
                    if (hlo_count > 40) {
                        clearInterval(intervalID);
                    }
                }, 250);
                """,
            )

            # Javascript above happens async
            time.sleep(11)
            see_more: WebElement = self.find_element(
                By.XPATH,
                "//div[@id = 'productOverview_feature_div']"
                "//span[contains(@class, 'a-expander-prompt')]"
                "[contains(text(), 'See more')]",
            )
            if see_more and see_more.is_displayed():
                see_more.click()

            read_more: WebElement = self.find_element(
                By.XPATH,
                "//div[@id = 'bookDescription_feature_div']"
                "//span[contains(@class, 'a-expander-prompt')]"
                "[contains(text(), 'Read more')]",
            )
            if read_more and read_more.is_displayed():
                read_more.click()

            self.browser_cleanup_item_page()
            item_html_filename = self.part_to_filename(
                PagePart.ORDER_ITEM,
                order_id=order_id,
                item_id=item_id,
                ext="html",
            )

            self.log.debug(
                "Saving item %s HTML to %s", item_id, item_html_filename
            )

            self.write(item_html_filename, self.browser.page_source, html=True)
            self.append_thumnails_to_item_html()
        else:
            self.log.debug("Item page for %s has been removed", item_id)
            item_dict["removed"] = True

        self.log.debug("Printing page to PDF")
        brws.execute_script("window.print();")

        self.wait_for_stable_file(self.cache["PDF_TEMP_FILENAME"])
        item_pdf_file = (
            order_cache_dir / Path(f"item-{item_id}.pdf")
        ).resolve()
        item_dict["pdf"] = str(
            Path(item_pdf_file).relative_to(self.cache["BASE"])
        )
        self.move_file(self.cache["PDF_TEMP_FILENAME"], item_pdf_file)
        self.log.debug("PDF moved to cache")

        brws.close()
        self.log.debug("Closed page for item %s", item_id)

    def browser_cleanup_item_page(self) -> None:
        brws = self.browser
        self.log.debug("Hide fluff, ads, etc")
        elemets_to_hide: List[WebElement] = []

        for element_xpath in [
            (
                "//table[@id='productDetails_warranty_support_sections']"
                "/parent::div/parent::div"
            ),
            (
                "//table[@id='productDetails_feedback_sections']"
                "/parent::div/parent::div"
            ),
        ]:
            elemets_to_hide += brws.find_elements(By.XPATH, element_xpath)

        for element_id in [
            "aplusBrandStory_feature_div",
            "ask-btf_feature_div",
            "customer-reviews_feature_div",
            "discovery-and-inspiration_feature_div",
            "dp-ads-center-promo_feature_div",
            "HLCXComparisonWidget_feature_div",
            "navFooter",
            "navbar",
            "orderInformationGroup",
            "productAlert_feature_div",
            "promotions_feature_div",
            "rhf-container",
            "rhf-frame",
            "rightCol",
            "sellYoursHere_feature_div",
            "similarities_feature_div",
            "value-pick-ac",
            "valuePick_feature_div",
            "sponsoredProducts2_feature_div",
            "sims-themis-sponsored-products-2_feature_div",
            "climatePledgeFriendlyBTF_feature_div",
            "aplusSustainabilityStory_feature_div",
            "accessories-and-compatible-products_feature_div",
            "ad-display-center-1_feature_div",
            "seo-related-keywords-pages_feature_div",
            "issuancePriceblockAmabot_feature_div",
            "b2bUpsell_feature_div",
            "merchByAmazonBranding_feature_div",
            "alternativeOfferEligibilityMessaging_feature_div",
            "followTheAuthor_feature_div",
            "moreAboutTheAuthorCard_feature_div",
            "showing-breadcrumbs_div",
            "gridgetWrapper",
            "gringottsPersistentWidget_feature_div",
            "va-related-videos-widget_feature_div",
            "nav-top",
            "skiplink",
            "wayfinding-breadcrumbs_container",
            "tp-inline-twister-dim-values-container",
            "poToggleButton",
        ]:
            elemets_to_hide += brws.find_elements(By.ID, element_id)

        for css_selector in [
            "div.a-carousel-container",
            "div.a-carousel-header-row",
            "div.a-carousel-row",
            "div.ad",
            "div.adchoices-container",
            "div.copilot-secure-display",
            "div.outOfStock",
            # share-button, gives weird artefacts on PDF
            "div.ssf-background",
            # share-button, gives weird artefacts on PDF (co.jp)
            "div.ssf-background-float",
            "div.widgetContentContainer",
            "div.vse-vwdp-video-block-wrapper",
            "div#variation_style_name ul",
        ]:
            elemets_to_hide += brws.find_elements(By.CSS_SELECTOR, css_selector)

        for element in [
            (By.TAG_NAME, "hr"),
            (By.TAG_NAME, "iframe"),
        ]:
            elemets_to_hide += brws.find_elements(element[0], element[1])
        try:
            center_col = brws.find_element(
                By.CSS_SELECTOR, "div.centerColAlign"
            )
        except NoSuchElementException:
            # co.jp?
            try:
                center_col = brws.find_element(
                    By.CSS_SELECTOR, "div.centerColumn"
                )
            except NoSuchElementException:
                # amazon fasion / apparel ?
                center_col = brws.find_element(By.CSS_SELECTOR, "div#centerCol")

        brws.execute_script(
            """
                // remove spam/ad elements
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].remove()
                }
                // Give product text more room
                arguments[1].style.marginRight=0
                // Turn om Amazon's special font
                arguments[2].classList.remove("a-ember");
                arguments[3].scrollIntoView()
                """,
            elemets_to_hide,
            center_col,
            brws.find_element(By.TAG_NAME, "html"),
            brws.find_element(By.ID, "leftCol"),
        )
        time.sleep(2)

    def browser_scrape_individual_order_list_page(
        self, year, start_index, order_list_html
    ):
        """
        Returns False when there are no more pages
        """
        self.log.debug(
            "Scraping order list for %s, index %s", year, start_index
        )
        if year != "archived":
            curr_url = self.ORDER_LIST_URL_TEMPLATE.format(
                year=year, start_index=start_index
            )
        else:
            curr_url = self.ORDER_LIST_ARCHIVED_URL_TEMPLATE.format(
                year=year, start_index=start_index
            )

        self.log.debug("Visiting %s", curr_url)
        brws = self.browser_visit_page(curr_url, goto_url_after_login=True)
        wait2 = WebDriverWait(brws, 2)

        empty_order_list = True

        try:
            wait2.until(
                EC.presence_of_element_located(
                    (By.XPATH, self.ORDER_CARD_XPATH)
                )
            )
            # If we found any order items
            # the order list is not empty
            empty_order_list = False
        except TimeoutException:
            pass

        if empty_order_list:
            # Empty order list, shotcut and save
            self.log.info("No orders on %s", year)

            order_list_html[(year, start_index)] = (
                self.save_order_list_cache_html_file(year, start_index)
            )
            return False

        # Non-empty order page
        self.log.debug("Page %s has orders", curr_url)
        try:
            num_orders = brws.find_element(
                By.XPATH, "//span[contains(@class, 'num-orders')]"
            )
            num_orders: int = int(re.match(r"^(\d+)", num_orders.text).group(1))
        except NoSuchElementException:
            num_orders = 0

        self.log.debug(
            "Total of %s orders, probably %s page(s)",
            num_orders,
            math.ceil(num_orders / 10),
        )

        found_next_button = False
        next_button_works = False
        try:
            next_button = brws.find_element(
                By.XPATH, "//li[contains(@class, 'a-last')]"
            )
            found_next_button = True
            next_button.find_element(By.XPATH, ".//a")
            next_button_works = True
        except NoSuchElementException:
            pass
        order_list_html[(year, start_index)] = (
            self.save_order_list_cache_html_file(year, start_index)
        )
        if num_orders <= 10:
            self.log.debug("This order list (%s) has only one page", year)
            if found_next_button:
                self.log.critical(
                    'But we found a "Next" button. '
                    "Don't know how to handle this..."
                )
                raise RuntimeError("See critical error above")
            return False

        return found_next_button and next_button_works

    # Init / Utility Functions

    def check_year(self, opt_years, start_year, not_archived):  # FIN
        years = list()
        if opt_years and start_year:
            self.log.error("cannot use both --year and --start-year")
            raise RuntimeError("cannot use both --year and --start-year")
        if opt_years:
            opt_years = sorted(set(int(year) for year in opt_years.split(",")))
            if any(
                year > datetime.date.today().year or year < 1990
                for year in opt_years
            ):
                err = (
                    "one or more years in --year is in the future or to"
                    " distant past:"
                    f" {', '.join(str(year) for year in opt_years)}"
                )
                self.log.error(err)
                raise RuntimeError(err)
            years = opt_years
        elif start_year:
            if start_year > datetime.date.today().year or start_year < 1990:
                err = (
                    "The year in --start-year is in the future or to distant"
                    f" past: {start_year}"
                )
                self.log.error(err)
                raise RuntimeError(err)
            years = sorted(range(start_year, datetime.date.today().year + 1))
        else:
            years = [datetime.date.today().year]
        log_msg = f"Will scrape {', '.join(str(year) for year in years)}"
        if not not_archived:
            log_msg += " and archived orders"
            years.append("archived")
        else:
            log_msg += " and not archived orders"

        self.log.info(log_msg)
        return years

    def check_tld(self, tld):  # FIN
        statuses = {
            0: "Tested. Should work fine.",
            1: "Will probably work with zero or minor monifications.",
            2: "Formerly souq.com, modifications may be required.",
            3: "Formerly joyo.com, modifications may be required.",
            4: "Unknown Amazon TLD, totally unknown if it will work or not.",
        }
        # https://en.wikipedia.org/wiki/Amazon_(company)#Amazon.com
        amazones = {
            "at": ("Austria (redirects to amazon.de)", 0),
            "de": ("Germany", 0),
            "com": ("United States", 0),
            "co.uk": ("United Kingdom", 0),
            "co.jp": ("Japan", 0),
            "es": ("Spain", 0),
            "se": ("Sweden", 0),
            "com.br": ("Brazil", 1),
            "ca": ("Canada", 1),
            "com.mx": ("Mexico", 1),
            "in": ("India", 1),
            "sg": ("Singapore", 1),
            "tr": ("Turkey", 1),
            "com.be": ("Belgium", 1),
            "fr": ("France", 1),
            "it": ("Italy", 1),
            "nl": ("Netherlands", 1),
            "pl": ("Poland", 1),
            "au": ("Australia", 1),
            "cn": ("China", 2),
            "eg": ("Egypt", 3),
            "sa": ("Saudi Arabia", 3),
            "ae": ("United Arab Emirates", 3),
        }
        if tld not in amazones:
            self.log.error(
                RED("Site: amazon.%s. %s"),
                tld,
                statuses[4],
            )
        elif amazones[tld][1] in [2, 3]:
            self.log.warning(
                AMBER("Site: amazon.%s. %s. %s"),
                tld,
                amazones[tld][0],
                statuses[amazones[tld][1]],
            )
        elif amazones[tld][1] == 1:
            self.log.warning(
                BLUE("Site: amazon.%s. %s. %s"),
                tld,
                amazones[tld][0],
                statuses[amazones[tld][1]],
            )
        else:
            self.log.info(
                GREEN("Site: amazon.%s. %s. %s"),
                tld,
                amazones[tld][0],
                statuses[amazones[tld][1]],
            )
        return tld

    def part_to_filename(self, part: PagePart, **kwargs):
        template: str
        if part == PagePart.ORDER_LIST_JSON:
            template = self.ORDER_LIST_JSON_FILENAME_TEMPLATE
        elif part == PagePart.ORDER_LIST_HTML:
            template = self.ORDER_LIST_HTML_FILENAME_TEMPLATE
        elif part == PagePart.ORDER_DETAILS:
            template = self.ORDER_FILENAME_TEMPLATE
        elif part == PagePart.ORDER_ITEM:
            template = self.ORDER_ITEM_FILENAME_TEMPLATE
        return Path(template.format(**kwargs))

    def setup_templates(self):
        # pylint: disable=invalid-name
        # URL Templates
        self.ORDER_LIST_URL_TEMPLATE = (
            f"https://www.amazon.{self.TLD}/gp/css/order-history?"
            "orderFilter=year-{year}&startIndex={start_index}"
        )
        self.ORDER_LIST_ARCHIVED_URL_TEMPLATE = (
            f"https://www.amazon.{self.TLD}/gp/your-account/order-history"
            "?&orderFilter=archived&startIndex={start_index}"
        )

        self.ORDER_URL_TEMPLATE = (
            f"https://www.amazon.{self.TLD}/"
            "gp/your-account/order-details/?ie=UTF8&orderID={order_id}"
        )

        self.ITEM_URL_TEMPLATE = (
            f"https://www.amazon.{self.TLD}/"
            "-/en/gp/product/{item_id}/?ie=UTF8"
        )
        # File name templates
        self.ORDER_LIST_HTML_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDER_LISTS"]
            / Path("order-list-{year}-{start_index}.html")
        )
        self.ORDER_LIST_JSON_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDER_LISTS"] / Path("order-list-{year}.json")
        )
        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/order.{ext}")
        )
        self.ORDER_ITEM_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/item-{item_id}.{ext}")
        )

    def skip_order(self, order_id: str, count: int) -> bool:
        if order_id.startswith("D01"):
            # self.log.info(
            #    (
            #        "Digital orders (%s) is PITA to scrape, "
            #        "so we don't support them for now"
            #    ),
            #    order_id,
            # )
            return True
        if ((self.AMZ_ORDERS and order_id not in self.AMZ_ORDERS)) or (
            order_id in settings.AMZ_ORDERS_SKIP
        ):
            # self.log.info("Skipping order ID %s", order_id)
            return True
        if settings.AMZ_ORDERS_MAX > 0:
            if count == (settings.AMZ_ORDERS_MAX + 1):
                pass
                # self.log.info(
                #    "Scraped %s order(s), breaking",
                #    settings.ALI_ORDERS_MAX,
                # )
            if count > settings.AMZ_ORDERS_MAX:
                return True
        return False
