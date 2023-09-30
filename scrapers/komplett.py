# pylint: disable=unused-import
import base64
from decimal import Decimal
import re
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Union
from urllib.parse import urlparse, urlencode, parse_qs
import requests
import filetype
import urllib.request

from selenium.common.exceptions import (
    WebDriverException,
    NoSuchElementException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from . import settings
from .base import BaseScraper

# pylint: disable=unused-import
from .utils import AMBER, BLUE, GREEN, RED


class KomplettScraper(BaseScraper):
    tla: Final[str] = "KMP"
    name: Final[str] = "Komplett"
    simple_name: Final[str] = "komplett"

    def __init__(self, options: Dict):
        super().__init__(options, __name__)
        self.setup_cache(self.simple_name)
        self.setup_templates()

    def command_scrape(self):
        try:
            order_dict = self.browser_scrape_order_list()
            for order_id, order_dict in order_dict.items():
                # nyeste: 204547164
                # pc med childitems 204139923
                # tre items, 200633800
                # gavekort 203867530
                # siste: 15478583
                # if order_id not in [
                #    "204547164", "200633800", "203867530", "15478583", "204139923"
                # ]:
                #    continue
                order_dir = Path(self.ORDER_FOLDER_TP.format(order_id=order_id))
                self.makedir(order_dir)
                order_json_file = Path(order_dir) / f"{order_id}.json"
                if self.can_read(order_json_file):
                    self.log.debug("Found JSON for order %s", order_id)
                    continue

                self.log.debug("Scraping order id %s", order_id)
                self.browser_visit(f"https://www.komplett.no/orders/{order_id}")

                order_infos: List[WebElement] = self.find_elements(
                    By.CSS_SELECTOR,
                    "div.order div.order-details div.info-row table",
                )
                assert len(order_infos) == 2, "Found !2 order info tables"
                for order_info in order_infos:
                    order_info_type = order_info.find_element(
                        By.CSS_SELECTOR, "caption"
                    ).text.strip()
                    assert order_info_type in [
                        "Ordredetaljer",
                        "Levering",
                    ], f"Unknown order_info_type: '{order_info_type}'"
                    order_dict[order_info_type] = {}
                    rows: List[WebElement] = order_info.find_elements(
                        By.CSS_SELECTOR, "tbody tr"
                    )
                    for row in rows:
                        label = row.find_element(By.TAG_NAME, "th").text.strip()
                        value = row.find_element(By.TAG_NAME, "td")
                        if anchor_element := self.find_element(
                            By.TAG_NAME, "a", value
                        ):
                            # td contains a anhor element, it is a link to a file
                            value = anchor_element.text.strip()
                            name_file_safe = base64.urlsafe_b64encode(
                                value.encode("utf-8")
                            ).decode("utf-8")
                            attachement_file = (
                                Path(order_dir)
                                / f"attachement-{name_file_safe}.pdf"
                            )
                            if label not in order_dict[order_info_type]:
                                order_dict[order_info_type][label] = []
                            order_dict[order_info_type][label].append(value)
                            if self.can_read(attachement_file):
                                self.log.debug(
                                    "We already have the file for '%s' saved",
                                    attachement_file.name,
                                )
                            else:
                                self.log.debug("Downloading: %s", value)
                                self.clear_folder()
                                brws = self.browser_get_instance()
                                old_handle = brws.current_window_handle
                                anchor_element.click()
                                time.sleep(2)
                                not_auto_download = len(brws.window_handles) > 1
                                if not_auto_download:
                                    self.log.debug(
                                        "PDF was not auto downloaded. Probably"
                                        " 404."
                                    )
                                    assert len(brws.window_handles) == 2
                                    for handle in brws.window_handles:
                                        if handle != old_handle:
                                            brws.switch_to.window(handle)
                                            break
                                    brws.execute_script("window.print();")
                                files = self.wait_for_files("*.pdf")
                                if not_auto_download:
                                    brws.close()
                                    brws.switch_to.window(old_handle)
                                assert (
                                    len(files) == 1
                                ), "Found more than one file when downloading"
                                file = files[0]
                                assert (
                                    file.suffix == ".pdf"
                                ), f"Found {file.suffix} when expecting PDF"
                                self.move_file(file, attachement_file)
                                self.log.debug(
                                    "Saved '%s' for order id %s",
                                    attachement_file.name,
                                    order_id,
                                )
                        else:
                            value = value.text.strip()
                            # self.log.debug("%s: %s", label, value)
                            order_dict[order_info_type][label] = value

                if "items" not in order_dict:
                    order_dict["items"] = []
                item_id = None
                for item_row in self.find_elements(
                    By.CSS_SELECTOR,
                    "div.order table.products-table tbody tr.table-row",
                ):
                    item_dict = {}
                    # We do some hacks for items that have childs, like computer builds
                    quantity = None
                    price = None
                    total = None
                    skip_thumb = False
                    if self.find_element(By.CSS_SELECTOR, ".child", item_row):
                        quantity = 1
                        price = "0"
                        total = "0"
                        skip_thumb = True

                    description_td = item_row.find_element(
                        By.CSS_SELECTOR, "td.description-col"
                    )
                    name_element = description_td.find_element(
                        By.CSS_SELECTOR, "p.webtext1"
                    )
                    name = name_element.text.strip()
                    if name == "Gavekort":
                        item_id = "giftcard"
                    else:
                        anchor_element = name_element.find_element(
                            By.XPATH, ".//ancestor::a"
                        )
                        href = anchor_element.get_attribute("href")
                        item_id = re.match(r".*/product/(\d*).*", href).group(1)
                        self.log.debug("Item ID: %s", item_id)
                    try:
                        description = description_td.find_element(
                            By.CSS_SELECTOR, "p.webtext2"
                        ).text.strip()
                    except NoSuchElementException:
                        description = ""
                    try:
                        int_ext_sku = description_td.find_element(
                            By.CSS_SELECTOR, "p.sku-text"
                        ).text.strip()
                        ext_sku = re.sub(
                            r"Varenr: .* / Prodnr:", "", int_ext_sku
                        ).strip()
                    except NoSuchElementException:
                        ext_sku = ""
                    if quantity is None:
                        quantity = item_row.find_element(
                            By.CSS_SELECTOR, "td.quantity-container"
                        ).text.strip()
                        price = item_row.find_element(
                            By.CSS_SELECTOR, "td.price"
                        ).text.strip()
                        total = item_row.find_element(
                            By.CSS_SELECTOR, "td.total"
                        ).text.strip()

                    if item_id != "giftcard" and not skip_thumb:
                        thumb_element_src: str = item_row.find_element(
                            By.CSS_SELECTOR, "td.image-col img"
                        ).get_attribute("src")
                        self.browser_get_item_thumb(
                            order_dir,
                            item_id,
                            thumb_element_src,
                            order_page=True,
                        )

                    item_dict["id"] = item_id
                    assert name
                    assert description is not None
                    assert ext_sku is not None
                    assert price is not None
                    assert quantity
                    assert total is not None
                    item_dict["name"] = name
                    item_dict["description"] = description
                    item_dict["ext_sku"] = ext_sku
                    item_dict["quantity"] = quantity
                    item_dict["price"] = price
                    item_dict["total"] = total
                    order_dict["items"].append(item_dict)
                if "pricing" not in order_dict:
                    order_dict["pricing"] = {}
                for row in self.find_elements(
                    By.CSS_SELECTOR,
                    "div.order div.product-list-footer table tr",
                ):
                    tds = row.find_elements(By.CSS_SELECTOR, "td")

                    order_dict["pricing"][tds[0].text.strip()] = tds[
                        1
                    ].text.strip()

                for item in order_dict["items"]:
                    if item["id"] == "giftcard":
                        continue
                    # We save in our own loop since we are finished with the order page
                    self.browser_save_item_page(item["id"], order_dir)
                self.write(order_json_file, order_dict, to_json=True)
                self.log.debug("Saved order %s to JSON", order_id)
        except NotImplementedError as nie:
            self.log.error(str(nie))
            self.browser_safe_quit()
        except WebDriverException as wbe:
            self.log.error(str(wbe))
            self.log.error(
                RED(
                    "If error was about an error page, please close all tabs, "
                    "clear all"
                    " history. Then restart the browser and log into Komplett."
                    " Lastly, close the browser and restart the script"
                )
            )
            self.browser_safe_quit()

    def browser_scrape_order_list(self):
        if self.options.use_cached_orderlist and self.can_read(
            self.ORDER_LIST_JSON
        ):
            order_dict = self.read(self.ORDER_LIST_JSON, from_json=True)
        else:
            order_dict = {}
            brws = self.browser_visit("https://www.komplett.no/orders")
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(2)
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(2)
            show_more: WebElement = self.find_element(
                By.XPATH, "//span[normalize-space(text())='Vis mer']"
            )
            while show_more and show_more.is_displayed():
                show_more.click()
                time.sleep(2)
                brws.execute_script(
                    "window.scrollTo(0,document.body.scrollHeight)"
                )
                time.sleep(2)
                brws.execute_script(
                    "window.scrollTo(0,document.body.scrollHeight)"
                )
                show_more: WebElement = self.find_element(
                    By.XPATH, "//span[normalize-space(text())='Vis mer']"
                )

            order_element: WebElement
            for order_element in self.find_elements(
                By.XPATH,
                "//section[contains(@class,'tidy-orders-list')]/article/table/tbody/tr",
            ):
                order_id = order_element.find_element(
                    By.CSS_SELECTOR, "td.order-number"
                ).text.strip()
                order_status = order_element.find_element(
                    By.CSS_SELECTOR, "td.status"
                ).text.strip()
                order_dict[order_id] = {"status": order_status}

        self.write(self.ORDER_LIST_JSON, order_dict, to_json=True)
        return order_dict

    def browser_save_item_page(self, item_id: str, order_dir: Path):
        item_pdf_file = order_dir / f"item-{item_id}.pdf"

        if self.can_read(item_pdf_file):
            self.log.debug("Found PDf for item %s", item_id)
            return
        self.log.debug("Visiting item %s", item_id)
        brws = self.browser_visit(
            f"https://www.komplett.no/product/{item_id}?noredirect=true"
        )
        thumbs = self.find_elements(
            By.CSS_SELECTOR, "div.product-images__thumb-carousel img"
        )
        if len(thumbs) > 0:
            thumb_src = thumbs[0].get_attribute("src")
            for thumb in thumbs:
                thumb_src = thumb.get_attribute("src")
                if not re.search(r"_\d*\.", thumb_src):
                    break
        else:
            thumb_src = self.find_element(
                By.CSS_SELECTOR,
                "div.product-images__main-carousel"
                " div.medium-image-carousel img",
            ).get_attribute("src")
        self.browser_get_item_thumb(order_dir, item_id, thumb_src)
        self.browser_cleanup_item_page()
        self.clear_folder()
        brws.execute_script("window.print();")
        files = self.wait_for_files("*.pdf")
        assert len(files) == 1, "Got more than one file when printing item PDF"
        file = files[0]
        self.move_file(file, item_pdf_file)
        self.log.debug("Saved PDF print of item page for %s", item_id)

    def browser_get_item_thumb(self, order_dir, item_id, src, order_page=False):
        thumb_url = re.sub(
            r"(.*)(/p/\d*/)(.*)",
            "\\1/p/1000/\\3",
            src,
        )
        if order_page:
            image_path = Path(order_dir) / f"item-{item_id}-order-thumb.jpg"
        else:
            image_path = Path(order_dir) / f"item-{item_id}-thumb.jpg"

        if not self.can_read(image_path):
            self.log.debug("Downloading %s", thumb_url)

            self.browser.execute_script(
                """
                            dwimg = document.createElement('img');
                            dwimg.src = arguments[0];
                            dwimg.id = "image-to-download"
                            document.body.appendChild(dwimg);
                        """,
                thumb_url,
            )
            # Wait for image load
            wait_count = 0
            while True:
                self.log.debug("Waiting for image to download")
                time.sleep(2)
                if int(self.browser.execute_script("""
                                return document.querySelector('#image-to-download').naturalWidth
                            """)) > 0:
                    # .complete does not work in Firefox sometimes?
                    break
                wait_count += 1
                if wait_count > 60:
                    self.log.error(
                        RED(
                            "We have been waiting for a file for 3 minutes,"
                            " something is wrong..."
                        )
                    )
                    raise NotImplementedError(f"{thumb_url}")
            image_dataurl: str = self.browser.execute_script("""
                            const canvas = document.createElement('canvas');
                            dwimg = document.querySelector('#image-to-download');
                            canvas.width = dwimg.naturalWidth;
                            canvas.height = dwimg.naturalHeight;
                            const ctx = canvas.getContext('2d');
                            ctx.drawImage(dwimg, 0, 0);
                            img_data = canvas.toDataURL('image/jpeg');
                            dwimg.remove()
                            canvas.remove()
                            return img_data
                        """)

            # data:image/jpeg;base64,
            assert len(image_dataurl) > 23
            self.log.debug(image_dataurl[0:50])
            response = urllib.request.urlopen(image_dataurl)
            self.write(image_path, response.file.read(), binary=True)
            self.log.debug("Thumbnail for %s saved to %s", item_id, image_path)
        else:
            self.log.debug("Thumbnail for %s found", item_id)

    def browser_cleanup_item_page(self):
        brws = self.browser_get_instance()
        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")

        time.sleep(2)
        brws.execute_script("""
            // shuffle some stuff
            mc = document.querySelector('main#MainContent');
            bdy = document.querySelector('body');
            bdy.prepend(mc);
            while (bdy.lastChild != mc) { bdy.lastChild.remove(); }

            // remove some obvious stuff
            [
            'div.menu-bar',
            'div.breadcrumbs-wrapper',
            'section.reviews',
            'div.comparison-widget-wrapper',
            'div.alert-wrapper',
            'div#videoly-videobox-placeholder',
            'videoly-tape'
            ].forEach((e) => {f=document.querySelector(e); if(f){f.remove()}});

            // remove some obvious stuff #2
            [
            'div.recommendations-extended'
            ].forEach((e) => { 
                document.querySelectorAll(e).forEach((f) =>{
                f.parentElement.remove();
                })
            });

            // remove evernything but some stuyff we don't
            document.querySelectorAll("div.productMainInfo-completeGrid > div").forEach(
            (e) => {
            keep = ['webtext1','productCarusel','hightlights'];
            for (let i = 0; i < keep.length; i++) {
                f=e.getAttribute("class").toLowerCase()
                if ( f.search(keep[i].toLowerCase()) >= 0 ) {return;}}
                e.remove();
            }
            );

            document.querySelector("div.product-sections-left").style.width="100%" ;

            // custom font can make print difficult
            document.querySelectorAll('*').forEach(function(e){
                                e.style.fontFamily = "sans-serif";
                                e.style.lineHeight = "1";
                            });


            document.querySelectorAll("div.product-section-content").forEach(function(e){
            e.style.display="block";
            e.style.float="unset";
            })

            document.querySelectorAll("div.product-section-content div").forEach(function(e){
            e.style.float="unset";
            })


            document.querySelectorAll("figure").forEach(function(e){e.style.pageBreakInside="avoid";})

            
            document.body.style.display="unset";
            document.querySelector("div.productMainInfo-completeGrid").style.display="unset";


            images=new Set();
            main_image = null;

            carousel = document.querySelectorAll("div.product-images__thumb-carousel img");
            if (carousel.length) {
            document.querySelectorAll("div.product-images__thumb-carousel img").forEach(
                function(e){
                images.add(e.src.replace(/p\/\d*\//, 'p/1000/'));
                }
            ); 
            main_image = images[0];
            images.forEach((e)=>{if (e.search('_\d*\.') == -1) {main_image =e;}});
            } else {
            main_image = document.querySelector("div.product-images__main-carousel div.medium-image-carousel img").src.replace(/p\/\d*\//, 'p/1000/');
            }

            images.delete(main_image)

            dpi = document.querySelector("div.product-images")
            while (dpi.lastChild) { dpi.lastChild.remove(); }

            img = document.createElement("img");
            img.src=main_image;
            img.style.maxWidth="100%" 
            dpi.appendChild(img);

                            
            document.body.lastChild.appendChild(document.createElement("br"));
            document.body.lastChild.appendChild(document.createElement("br"));
            document.body.lastChild.appendChild(document.createElement("br"));
            images.forEach((e) => {
            img = document.createElement("img");
            img.src=e;
            img.style.maxWidth="100%"
            img.style.pageBreakInside="avoid";
            document.body.lastChild.appendChild(img);
            
            });

            document.querySelectorAll("div.product-section-content img").forEach(function(e){
            e.style.pageBreakInside="avoid";
            e.parentElement.style.pageBreakInside="avoid";
            })



            document.querySelectorAll("iframe").forEach(function(e){
            video = e.src
            if (!video.startsWith("https://www.youtube")) { return;}
            parent = e.parentElement;
            np = parent;
            e.remove();
            video_parent = null;
            for (let i = 0; i < 10; i++) {
                c = np.parentElement.getAttribute("class");
                if (c && (c.toLowerCase().search('video') >= 0)){
                    if (!np.parentElement) {
                            return
                    }
                    video_parent = np.parentElement;
                }
                np = np.parentElement;
            }
            if (video_parent) {
                parent = video_parent.parentElement;
            }
            p = document.createElement("p");
            p.className ="youtube-replacement" 
            p.innerText = video;
            if (parent.querySelectorAll("iframe").length == 0) {
                if (video_parent) {
                    while (video_parent.lastChild) {  
                        video_parent.lastChild.remove(); 
                    }
                }
            }
            parent.parentElement.appendChild(p);
            })
        """)
        time.sleep(2)
        brws.execute_script("""
            [
            'videoly-tape'
            ].forEach((e) => {f=document.querySelector(e); if(f){f.remove()}});
        """)
        time.sleep(1)
        brws.execute_script("""
            document.querySelectorAll("button.read-more-toggle").forEach(function(e){e.scrollIntoView();e.click();})
        """)

    def _browser_post_init(self):
        # Visit the front page first, so we can make sure we are logged in
        # Komplett has a paranoid bot detector on the login page
        self.browser_visit("https://komplett.no")
        return

    def browser_detect_handle_interrupt(self, expected_url):
        brws = self.browser_get_instance()
        if "login" in brws.current_url:
            # Somehow we have ended up on the login page
            self.log.error(
                RED(
                    "Please open the browser profile manually and clear all"
                    " history. Then restart the browser and log into Komplett."
                    " Lastly, close the browser and restart the script"
                )
            )
            raise NotImplementedError()

        if cookie_consent := self.find_element(
            By.CSS_SELECTOR, ".cookie-consent-popup"
        ):
            for cookie_button in cookie_consent.find_elements(
                By.CSS_SELECTOR, "button"
            ):
                if re.search(
                    r"godta alle", cookie_button.text.strip(), re.IGNORECASE
                ):
                    cookie_button.click()
                    break
        if user_profile_span := self.find_element(
            By.CSS_SELECTOR,
            ".user-profile__wrapper .user-profile__container span",
        ):
            if re.search(
                r"logg inn", user_profile_span.text.strip(), re.IGNORECASE
            ):
                self.log.error(
                    RED(
                        "Please open the browser profile manually and clear all"
                        " history. Then restart the browser and log into"
                        " Komplett. Lastly, close the browser and restart the"
                        " script"
                    )
                )
                raise NotImplementedError()
        else:
            self.log.warning(
                AMBER("User profile element not found. Login check failed.")
            )

    def setup_templates(self):
        # pylint: disable=invalid-name
        self.ORDER_LIST_JSON = self.cache["BASE"] / "order_list.json"
        self.ORDER_FOLDER_TP = str(self.cache["BASE"] / "orders/{order_id}/")

    def command_to_std_json(self):
        structure = self.get_structure(
            self.name,
            None,
            "https://www.komplett.no/orders/{order_id}",
            "https://www.komplett.no/product/{item_id}?noredirect=true",
        )

        order_lists: Dict = self.read(self.ORDER_LIST_JSON, from_json=True)
        statuses = set([x["status"] for x in order_lists.values()])
        known_statuses = ["Sendt", "Levert", "Kansellert"]
        export_statuses = ["Sendt", "Levert"]
        for status in statuses:
            if status not in known_statuses:
                self.log.error(
                    "Unknown status '%s', code update required.", status
                )
                raise NotImplementedError()
        structure["orders"] = []
        for order_id in [
            key
            for key, value in order_lists.items()
            if value["status"] in export_statuses
        ]:
            self.log.debug("Processing order %s", order_id)
            order_dir = Path(self.ORDER_FOLDER_TP.format(order_id=order_id))
            orig_order = self.read(
                order_dir / f"{order_id}.json", from_json=True
            )

            order_dict = {
                "id": order_id,
                "date": (
                    datetime.strptime(
                        orig_order["Ordredetaljer"]["Bestilt"], "%d/%m/%Y %H:%M"
                    )
                    .date()
                    .isoformat()
                ),
                "items": [],
                "extra_data": {},
                "total": self.get_value_currency(
                    "total", orig_order["pricing"]["Totalt"], "NOK"
                ),
                "shipping": self.get_value_currency(
                    "total", orig_order["pricing"]["Frakt"], "NOK"
                ),
            }
            for attachement in order_dir.glob("attachement-*.pdf"):
                if "attachements" not in order_dict:
                    order_dict["attachements"] = []
                name = base64.urlsafe_b64decode(attachement.stem.split("-")[1]).decode("utf-8")
                attachement_dict = {
                    "name": name,
                    "path": attachement.relative_to(
                        self.cache["BASE"]
                    ).as_posix(),
                }
                order_dict["attachements"].append(attachement_dict)

            del orig_order["Ordredetaljer"]["Bestilt"]
            del orig_order["pricing"]["Totalt"]
            del orig_order["pricing"]["Frakt"]
            if orig_order["pricing"] != {}:
                order_dict["extra_data"]["pricing"] = orig_order["pricing"]
            del orig_order["pricing"]

            for item in orig_order["items"]:
                item_id = item["id"]
                item_dict = {
                    "id": item_id,
                    "name": item["name"],
                    "quantity": int(item["quantity"]),
                    "extra_data": {},
                    "total": self.get_value_currency(
                        "total", str(item["total"]), "NOK"
                    ),
                }
                del item["id"]
                del item["name"]
                del item["quantity"]
                del item["total"]
                if "price" in item:
                    item["price"] = self.get_value_currency(
                        "total", str(item["price"]), "NOK"
                    )
                item_dict["extra_data"].update(item)
                if item_id != "giftcard":
                    assert self.can_read(
                        order_dir / f"item-{item_id}.pdf"
                    ), f"Can't read item PDF for {item_id}"
                    item_dict["attachements"] = [
                        {
                            "name": "Item PDF",
                            "path": (
                                Path(order_dir / f"item-{item_id}.pdf")
                                .relative_to(self.cache["BASE"])
                                .as_posix()
                            ),
                        }
                    ]
                thumb = None
                if self.can_read(order_dir / f"item-{item_id}-thumb.jpg"):
                    thumb = order_dir / f"item-{item_id}-thumb.jpg"
                elif self.can_read(
                    order_dir / f"item-{item_id}-order-thumb.jpg"
                ):
                    thumb = order_dir / f"item-{item_id}-order-thumb.jpg"
                if thumb:
                    item_dict["thumbnail"] = (
                        Path(thumb).relative_to(self.cache["BASE"]).as_posix()
                    )
                order_dict["items"].append(item_dict)
            del orig_order["items"]
            order_dict["extra_data"].update(orig_order)
            # self.pprint(order_dict)
            structure["orders"].append(order_dict)
        #self.pprint(structure)
        self.output_schema_json(structure)
