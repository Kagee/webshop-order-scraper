# pylint: disable=unused-import
import base64
import contextlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import parse_qs, urlencode, urlparse

import filetype
import requests
from PIL import Image
from selenium.common.exceptions import (
    NoSuchElementException,
    NoSuchWindowException,
)
from selenium.webdriver.common.by import By

from scrapers.utils import AMBER, RED

from .base import BaseScraper

if TYPE_CHECKING:
    from selenium.webdriver.remote.webelement import WebElement


class KjellScraper(BaseScraper):
    tla: Final[str] = "KJL"
    name: Final[str] = "Kjell.com"
    COUNTRY: Final[str] = "test"
    simple_name: Final[str] = "kjell.com"

    # Methods that use Selenium to scrape webpages in a browser

    def browser_save_item_and_attachments(
        self,
        order_id,
        order_cache_dir,
        item_id,
        line_item,
    ):
        item_pdf_file = (
            order_cache_dir / Path(f"item-{item_id}.pdf")
        ).resolve()
        item_pdf_missing = f"{item_pdf_file}.missing"

        if line_item["url"] != "":
            url = "https://kjell.com" + line_item["url"]

            if self.can_read(item_pdf_file) or self.can_read(
                item_pdf_missing,
            ):
                self.log.debug(
                    "Item %s has probably been scraped before, found page PDF.",
                    item_id,
                )
                return
            brws = self.browser_visit_page_v2(url)
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(2)
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")

            try:
                brws.find_element(
                    By.XPATH,
                    "//h1[contains(text(),'Finner ikke siden')]",
                )
            except NoSuchElementException:
                pass
            else:
                self.log.error(
                    RED("Item id %s in order %s, %s, returned 404: %s"),
                    item_id,
                    order_id,
                    line_item["displayName"],
                    url,
                )
                self.write(item_pdf_missing, "1")
                return

            self.browser_expand_item_page()

            self.save_support_documents(item_id, order_cache_dir)

            if not self.can_read(item_pdf_file) and not self.can_read(
                item_pdf_missing,
            ):
                self.browser_cleanup_item_page()
                self.log.debug("Printing page to PDF")
                self.remove(self.cache["PDF_TEMP_FILENAME"])

                brws.execute_script("window.print();")
                self.wait_for_stable_file(self.cache["PDF_TEMP_FILENAME"])

                self.move_file(
                    self.cache["PDF_TEMP_FILENAME"],
                    item_pdf_file,
                )
            else:
                self.log.debug("Skipping item PDF for %s", item_id)
        else:
            self.log.error(
                RED("Item id %s in order %s, %s has no url"),
                item_id,
                order_id,
                line_item["displayName"],
            )
            self.write(item_pdf_missing, "1")

    def browser_save_item_thumbnail(
        self,
        order_id,
        order_cache_dir,
        item_id,
        line_item,
    ):
        item_thumb_file = (
            order_cache_dir / Path(f"item-thumb-{item_id}.jpg")
        ).resolve()
        item_thumb_missing = f"{item_thumb_file}.missing"
        item_thumb_path = str(
            Path(item_thumb_file).relative_to(self.cache["BASE"]),
        )
        if self.can_read(item_thumb_file):
            self.log.debug(
                "Skipping thumb for item %s, found %s",
                item_id,
                item_thumb_file,
            )
            return None
        if self.can_read(item_thumb_missing):
            self.log.error(
                AMBER("Skipping thumb for item %s, found %s"),
                item_id,
                item_thumb_missing,
            )
            return None

        if line_item["imageUrl"]["url"] and line_item["imageUrl"]["url"] != "":
            image_url = "https://kjell.com" + line_item["imageUrl"]["url"]
            url_parsed = urlparse(image_url)

            query_parsed = parse_qs(url_parsed.query, keep_blank_values=True)
            query_parsed.pop("w", None)
            query_parsed.pop("h", None)
            query_parsed["w"] = "900"
            image_url = url_parsed._replace(
                query=urlencode(query_parsed, doseq=True),
            ).geturl()
            self.log.debug("Trying to download thumbnail: %s", image_url)
            headers = {
                "User-Agent": (
                    "python/webshop-order-scraper (hildenae@gmail.com)"
                ),
            }
            response = requests.get(url=image_url, headers=headers, timeout=10)
            self.remove(self.cache["IMG_TEMP_FILENAME"])
            self.write(
                self.cache["IMG_TEMP_FILENAME"],
                response.content,
                binary=True,
            )
            kind = filetype.guess(self.cache["IMG_TEMP_FILENAME"])

            if kind:
                if kind.mime.startswith("image/tif"):
                    im = Image.open(self.cache["IMG_TEMP_FILENAME"])
                    im.thumbnail(im.size)
                    im.save(
                        self.cache["IMG_TEMP_FILENAME"].with_suffix(".jpeg"),
                        "JPEG",
                        quality=80,
                    )
                    self.move_file(
                        old_path=self.cache["IMG_TEMP_FILENAME"].with_suffix(
                            ".jpeg",
                        ),
                        new_path=self.cache["IMG_TEMP_FILENAME"],
                    )
                kind = filetype.guess(self.cache["IMG_TEMP_FILENAME"])
                if kind.mime.startswith("image/") and kind.extension == "jpg":
                    self.log.debug(
                        "Downloaded thumbnail %s was: %s",
                        self.cache["IMG_TEMP_FILENAME"],
                        kind.extension,
                    )
                    self.move_file(
                        self.cache["IMG_TEMP_FILENAME"],
                        item_thumb_file,
                    )
                    return item_thumb_path
                self.log.error(
                    "Thumbnail was not image or JPEG: %s, %s",
                    kind.mime,
                    kind.extension,
                )
                self.write(item_thumb_missing, "1")
                return None
            self.log.error(
                RED("Failed to identify filetype: %s"),
                image_url,
            )
            self.write(item_thumb_missing, "1")
            return None
        self.log.error(
            RED("Item id %s in order %s, has no thumbnail"),
            item_id,
            order_id,
        )
        self.write(item_thumb_missing, "1")
        return None

    def browser_cleanup_item_page(self) -> None:
        brws = self.browser_get_instance()
        self.log.debug("Hide fluff, ads, etc")
        cookie_accept = None
        with contextlib.suppress(NoSuchElementException):
            cookie_accept = brws.find_element(
                By.XPATH,
                "//h4[contains(text(),'"
                " cookies')]/parent::div/div/button/span[contains(text(),"
                " 'Godta')]",
            )
        with contextlib.suppress(NoSuchElementException):
            cookie_accept = brws.find_element(
                By.XPATH,
                '//span[contains(text(),"Aksepterer")]/parent::button',
            )
        if cookie_accept:
            cookie_accept.click()
        elemets_to_hide: list[WebElement] = []

        for element_xpath in [
            # Top three navn divs including breadcrumbs
            '//div[@id="content-container"]/div[3]',
            '//div[@id="content-container"]/div[2]',
            '//div[@id="content-container"]/div[1]',
            # Some not interresting fold-outs
            '//span[contains(text(),"Kundeanmeldelser")]/ancestor::button/parent::div',
            '//span[contains(text(),"Sendinger")]/ancestor::button/parent::div',
            (
                '//span[contains(text(),"Passer bl.a.'
                ' til")]/ancestor::button/parent::div'
            ),
            '//span[contains(text(),"360")]/ancestor::button/parent::div',
            (
                '//span[contains(text(),"Kompletter kjøpet'
                ' ditt")]/ancestor::button/parent::div'
            ),
            (
                '//span[contains(text(),"Alltid trygt å handle hos'
                ' Kjell")]/parent::div/parent::div/parent::div/parent::div'
            ),
            (
                '//span[contains(text(),"Spør'
                ' Kjell")]/ancestor::button/parent::div/parent::div'
            ),
            # Warehouse stock info
            (
                '//h4[contains(text(),"Lagerstatus nett og i'
                ' butikk")]/parent::div/parent::div/parent::div/parent::div'
            ),
            # Live-stream video
            '//img[contains(@src,"liveshopping.bambuser.com")]/parent::div/parent::div',
            # 360 images
            '//img[contains(@src,"360images")]/parent::div/parent::div',
            # Add to cart and likes
            '//button[@data-test-id="add-to-shopping-list-button"]/parent::div',
            # Simmilar products
            (
                '//h4[contains(text(),"Lignende'
                ' produkter")]/parent::div/parent::div'
            ),
            (
                '//h3[contains(text(),"Fri'
                ' standardfrakt")]/parent::div/'
                "parent::div/parent::div/parent::div"
            ),
            (
                '//h3[contains(text(),"Går bra'
                ' med")]/parent::div/parent::div'
                "/parent::div/parent::div/parent::div"
            ),
            '//h4[contains(text(),"Kombiner med")]/parent::div',
            (
                '//button[contains(text(),"Gå til'
                ' kundeanmeldelsen")]/parent::div/parent::div'
            ),
            (
                '//button[contains(text(),"'
                ' kundeanmeldelse")]/parent::span/parent::div'
            ),
        ]:
            elemets_to_hide += brws.find_elements(By.XPATH, element_xpath)

        for element_id in [
            # Chat / reviews
            "imbox-launcher-container1900",
        ]:
            elemets_to_hide += brws.find_elements(By.ID, element_id)

        for css_selector in [
            # "div.a-carousel-container",
        ]:
            elemets_to_hide += brws.find_elements(By.CSS_SELECTOR, css_selector)

        for element in [
            (By.TAG_NAME, "iframe"),
        ]:
            elemets_to_hide += brws.find_elements(element[0], element[1])

        brws.execute_script(
            """
                // remove spam/ad elements
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].remove()
                }
                """,
            elemets_to_hide,
        )

        time.sleep(2)

    def browser_expand_item_page(self):
        brws = self.browser_get_instance()
        brws.execute_script(
            """
                sections = document.getElementsByTagName("section")
                for (let i = 0; i < sections.length; i++) {
                    sections[i].style.width = "100%"
                    sections[i].style.gridTemplateColumns = "none"
                    sections[i].style.display="block";
                }

                imgs = document.getElementsByTagName("img")
                for (let i = 0; i < imgs.length; i++) {
                    imgs[i].style.transitionTimingFunction = null;
                    imgs[i].style.transitionDuration = null;
                    imgs[i].style.transitionProperty= null;
                }

                element = document.getElementsByTagName("body")[0]
                element.style.fontFamily="none";

            """,
        )
        large_images = brws.find_elements(
            By.XPATH,
            '//img[contains(@intrinsicsize,"960")]',
        )
        try:
            thumbs_div = brws.find_element(
                By.XPATH,
                '(//img[contains(@intrinsicsize,"320")])[1]/parent::span/parent::div/parent::div',
            )
        except NoSuchElementException:
            self.log.debug("No thumbnail list")
            thumbs_div = None

        content_container = brws.find_element(
            By.CSS_SELECTOR,
            "div#content-container",
        )
        brws.execute_script(
            """
                arguments[1].style.display="block";
                var div = document.createElement('div');
                // large_images
                for (let i = 0; i < arguments[0].length; i++) {
                    var div2 = document.createElement('p');
                    div2.style.breakInside="avoid";
                    var img = document.createElement('img');
                    img.style.display="block";
                    img.style.breakInside="avoid";
                    img.style.width="960px";
                    new_url = new URL(arguments[0][i].src);
                    img.src = new_url.toString();
                    console.log(img.src)
                    div2.appendChild(img);
                    div.appendChild(div2);
                }
                document.body.appendChild(div);
                // thumbs_div
                if (arguments[2]) {
                    arguments[2].style.display="none";
                }

            """,
            large_images,
            content_container,
            thumbs_div,
        )
        for text_expand in ["Teknisk informasjon", "Support"]:
            with contextlib.suppress(NoSuchElementException):
                btn = brws.find_element(
                    By.XPATH,
                    f'//span[contains(text(),"{text_expand}")]/ancestor::button',
                )
                btn.click()

        figures = brws.find_elements(By.TAG_NAME, "figure")
        for figure in figures:
            time.sleep(0.5)
            brws.execute_script(
                """
                arguments[0].scrollIntoView();
            """,
                figure,
            )
        time.sleep(2)

    def save_support_documents(self, item_id, order_cache_dir):
        brws = self.browser_get_instance()
        attachments = []
        try:
            support_a = brws.find_elements(
                By.XPATH,
                '//span[contains(text(),"Support")]/ancestor::button/parent::div//a',
            )
            for a_element in support_a:
                if not a_element.get_attribute("href"):
                    continue
                self.log.debug("HREF: %s", a_element.get_attribute("href"))
                self.log.debug("TEXT: %s", a_element.text)
                url_parts = urlparse(a_element.get_attribute("href"))
                if url_parts.path.endswith(".pdf"):
                    orig_filename = Path(url_parts.path).name

                    filename = f"{orig_filename}--{a_element.text}"
                    filename_safe = base64.urlsafe_b64encode(
                        filename.encode("utf-8"),
                    ).decode("utf-8")

                    attachment_file = (
                        order_cache_dir
                        / Path(
                            f"item-attachment-{item_id}-{filename_safe}.pdf",
                        )
                    ).resolve()
                    if self.can_read(attachment_file):
                        self.log.debug(
                            "Skipping %s, already downloaded",
                            orig_filename,
                        )
                        continue
                    for pdf in self.cache["TEMP"].glob("*.pdf"):
                        # Remove old/random PDFs
                        pdf.unlink()
                    a_element.click()
                    self.log.debug(
                        "Opening PDF, waiting for it to download in background",
                    )
                    pdf = list(self.cache["TEMP"].glob("*.pdf"))
                    while not pdf:
                        pdf = list(self.cache["TEMP"].glob("*.pdf"))
                        self.log.debug("No pdf, waiting 3 sec")
                        time.sleep(3)
                    if len(pdf) > 1:
                        msg = (
                            "Found multiple PDFs after download, unknown"
                            " condition."
                        )
                        raise NotImplementedError(
                            msg,
                        )

                    self.wait_for_stable_file(pdf[0])

                    self.log.debug(
                        "Found %s, saving as %s.pdf (%s.pdf)",
                        pdf[0].name,
                        filename_safe,
                        filename,
                    )

                    attachments.append((a_element.text, str(attachment_file)))
                    self.move_file(pdf[0], attachment_file)
        except NoSuchElementException:
            pass
        return attachments

    def browser_load_order_list(self):
        if self.options.use_cached_orderlist:
            if self.can_read(self.ORDER_LIST_JSON_FILENAME):
                return self.read(self.ORDER_LIST_JSON_FILENAME, from_json=True)
            self.log.info("Could not find cached orderlist.")

        brws = self.browser_visit_page(
            self.ORDER_LIST_URL,
            default_login_detect=False,
        )
        time.sleep(2)
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.log.info(
                AMBER(
                    "Please log in to Kjell.com, and press <ENTER> when"
                    " ready...",
                ),
            )
            input()
        self.browser_visit_page(self.ORDER_LIST_URL)

        cookie_accept = None
        with contextlib.suppress(NoSuchElementException):
            cookie_accept = brws.find_element(
                By.XPATH,
                "//h4[contains(text(),'"
                " cookies')]/parent::div/div/button/span[contains(text(),"
                " 'Godta')]",
            )
        with contextlib.suppress(NoSuchElementException):
            cookie_accept = brws.find_element(
                By.XPATH,
                '//span[contains(text(),"Aksepterer")]/parent::button',
            )
        if cookie_accept:
            cookie_accept.click()

        # view-source:
        self.browser_visit_page(
            r"view-source:https://www.kjell.com/resolvedynamicdata?d=[{t:%22Avensia.Common.Features.Account.MyPages.MyTransactions.UserTransactions,Avensia.Common%22}]",
        )

        content = self.browser.find_element(By.XPATH, "//pre").text
        shop_data = json.loads(content)
        self.write(self.ORDER_LIST_JSON_FILENAME, shop_data, to_json=True)
        return shop_data

    # Random utility functions

    @classmethod
    def check_country(cls, country: str):
        country = country.lower()
        if country not in ["no", "se"]:
            msg = "Only supports Kjell.com/[no/se]"
            raise NotImplementedError(msg)
        return country

    def setup_templates(self):
        # pylint: disable=invalid-name
        # URL Templates
        self.ORDER_LIST_URL: str = {
            "no": "https://www.kjell.com/no/mine-sider/mine-kjop",
        }[self.COUNTRY]
        self.LOGIN_PAGE_RE: str = r"https://www.kjell.com.*login=required.*"

        # pylint: disable=invalid-name
        self.ORDER_LIST_JSON_FILENAME = (
            self.cache["ORDER_LISTS"] / f"kjell-{self.COUNTRY}-orders.json"
        )

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        pass

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your Kjell orders.
        """
        try:
            orders = self.browser_load_order_list()[0]
            products = {}
            code_len_max = 0
            code_len_min = 9999
            for pli in orders["productListItems"]:
                if pli["code"] not in products:
                    code_len_max = max(code_len_max, len(pli["code"]))
                    code_len_min = min(code_len_min, len(pli["code"]))
                    products[pli["code"]] = pli
                else:
                    msg = "Not implemented: Product code appeared twice"
                    raise NotImplementedError(
                        msg,
                    )
            self.log.debug(
                "Item code was from %s to %s chars",
                code_len_min,
                code_len_max,
            )
            order_dict = {}
            for order in orders["completed"]["items"]:
                order_dict[order["transactionNumber"]] = order

            for order_id, order in order_dict.items():
                order_cache_dir = self.cache["ORDERS"] / Path(order_id)
                self.makedir(order_cache_dir)
                for line_item in order["lineItems"]:
                    # Item codes are in general 5 numbers.
                    # Below that is bags etc.
                    item_id = line_item["code"]

                    if len(item_id) > 4:  # noqa: PLR2004
                        self.log.debug("Order: %s, item: %s", order_id, item_id)
                        self.browser_save_item_thumbnail(
                            order_id,
                            order_cache_dir,
                            item_id,
                            line_item,
                        )
                        self.browser_save_item_and_attachments(
                            order_id,
                            order_cache_dir,
                            item_id,
                            line_item,
                        )
        except NoSuchWindowException:
            pass
        self.browser_safe_quit()

    def command_to_std_json(self):  # noqa: PLR0912, PLR0915, C901
        """
        Convert all data we have to a JSON that validates with schema,
         and a .zip with all attachments
        """

        structure = self.get_structure(
            self.name,
            None,
            "https://www.kjell.com/no/mine-sider/mine-kjop#{order_id}",
            "https://www.kjell.com/-p{item_id}",
        )

        kjell_json = self.read(self.ORDER_LIST_JSON_FILENAME, from_json=True)[0]

        orders = []

        for orig_order in kjell_json["completed"]["items"]:
            order_id = orig_order["transactionNumber"]
            try:
                purchase_datetime = datetime.strptime(
                    orig_order["purchaseDate"],
                    "%Y-%m-%dT%H:%M:%S%z",
                )
            except ValueError:
                purchase_datetime = datetime.strptime(
                    orig_order["purchaseDate"],
                    "%Y-%m-%dT%H:%M:%S.%f%z",
                )

            order_object = {
                "id": order_id,
                "date": purchase_datetime.date().isoformat(),
                "items": [],
                "total": self.get_value_currency(
                    "total",
                    orig_order["total"],
                    "NOK",
                ),
                "tax": self.get_value_currency(
                    "tax",
                    orig_order["vatAmount"],
                    "NOK",
                ),
                "shipping": self.get_value_currency(
                    "shipping",
                    orig_order["shippingFee"]["exclVat"],
                    "NOK",
                ),
            }
            order_cache_dir = self.cache["ORDERS"] / Path(order_id)
            files = {}

            for file in order_cache_dir.glob("*"):
                if file.name.endswith(".missing"):
                    continue
                file_item_id = re.match(
                    r"^item-(?:thumb-|attachment-|)(\d*)(?:-|\.)",
                    file.name,
                ).group(1)
                if file_item_id not in files:
                    files[file_item_id] = {}
                item_file_type = "pdf"
                if file.name.startswith("item-thumb-"):
                    item_file_type = "thumb"
                elif file.name.startswith("item-attachment-"):
                    item_file_type = "attachments"

                if item_file_type not in files[file_item_id]:
                    files[file_item_id][item_file_type] = []
                files[file_item_id][item_file_type].append(file)

            for item in orig_order["lineItems"]:
                item_id = item["code"]
                if int(item_id) < 10:  # noqa: PLR2004
                    # Bags etc.
                    continue
                if not item["displayName"]:
                    prodname = re.match(
                        rf".*/([^/]*)-p{item['code']}.*",
                        item["url"],
                    ).group(1)
                    item["displayName"] = prodname.replace(
                        "-",
                        " ",
                    ).capitalize()
                item_dict = {
                    "id": item_id,
                    "name": item["displayName"],
                    "quantity": int(item["quantity"])
                    if item["quantity"].is_integer()
                    else item["quantity"],
                    "subtotal": self.get_value_currency(
                        "subtotal",
                        item["price"]["currentExclVat"],
                        "NOK",
                    ),
                    "vat": self.get_value_currency(
                        "vat",
                        item["price"]["vatAmount"],
                        "NOK",
                    ),
                    "total": self.get_value_currency(
                        "total",
                        item["price"]["currentInclVat"],
                        "NOK",
                    ),
                }
                if item_id in files:
                    if "thumb" in files[item_id]:
                        item_dict["thumbnail"] = (
                            Path(files[item_id]["thumb"][0])
                            .relative_to(self.cache["BASE"])
                            .as_posix()
                        )
                    if "pdf" in files[item_id]:
                        if "attachments" not in item_dict:
                            item_dict["attachments"] = []
                        item_dict["attachments"].append(
                            {
                                "name": "Item PDF",
                                "path": (
                                    Path(files[item_id]["pdf"][0])
                                    .relative_to(self.cache["BASE"])
                                    .as_posix()
                                ),
                            },
                        )
                    if "attachments" in files[item_id]:
                        if "attachments" not in item_dict:
                            item_dict["attachments"] = []
                        attachment: str
                        for attachment in files[item_id]["attachments"]:
                            item_dict["attachments"].append(
                                {
                                    "name": (
                                        base64.urlsafe_b64decode(
                                            attachment.name.split("-")[3]
                                            .split(".")[0]
                                            .encode("utf-8"),
                                        )
                                        .decode("utf-8")
                                        .split("--")[0]
                                    ),
                                    "path": (
                                        Path(attachment)
                                        .relative_to(self.cache["BASE"])
                                        .as_posix()
                                    ),
                                },
                            )

                del item["code"]
                del item["displayName"]
                del item["quantity"]
                del item["price"]["currentInclVat"]
                del item["price"]["vatAmount"]
                del item["price"]["currentExclVat"]

                item_dict["extra_data"] = item
                order_object["items"].append(item_dict)

            del orig_order["transactionNumber"]
            del orig_order["purchaseDate"]
            del orig_order["total"]
            del orig_order["vatAmount"]
            del orig_order["shippingFee"]["exclVat"]
            del orig_order["lineItems"]
            order_object["extra_data"] = orig_order
            orders.append(order_object)

        structure["orders"] = orders
        self.output_schema_json(structure)

    # Class init
    def __init__(self, options: dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        self.COUNTRY = self.check_country(options.country)
        self.simple_name = "kjell.com-" + self.COUNTRY
        super().setup_cache(Path("kjell-" + self.COUNTRY))
        self.setup_templates()
