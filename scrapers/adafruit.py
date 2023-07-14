import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Final, List

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from . import settings
from .base import BaseScraper, PagePart


class AdafruitScraper(BaseScraper):
    tla: Final[str] = "ADA"
    name: Final[str] = "Adafruit"
    simple_name: Final[str] = "adafruit"

    def __init__(self, options: Dict):
        super().__init__(options, __name__)
        self.setup_cache("adafruit")
        self.setup_templates()

    def usage(self):
        print(f"""
    USAGE:
    ==================================================
    Login to https://www.adafruit.com/
    Click "Account" -> "My Account" 
    Click "Order History" (https://www.adafruit.com/order_history)
    Click "Export Products CSV" and save "products_history.csv" to 
        {self.cache['BASE']}
    Click "Export Orders CSV" and save "order_history.csv" to 
        {self.cache['BASE']}
        """)

    def parse_order_csv(self):
        with open(self.ORDERS_CSV, newline="", encoding="utf-8") as csvfile:
            orders_dict = list(csv.DictReader(csvfile, dialect=csv.excel))
            orders = {}
            for order in orders_dict:
                order["date_purchased"] = datetime.strptime(
                    order["date_purchased"], "%Y %m %d %H:%M:%S"
                )
                orders[order["order_id"].split(" ")[0]] = order
            return orders

    def combine_orders_items(self, orders):
        with open(self.ITEMS_CSV, newline="", encoding="utf-8") as csvfile:
            items = list(csv.DictReader(csvfile, dialect=csv.excel))
        for item in items:
            order_id = item["order"]
            del item["order"]
            if "items" not in orders[order_id]:
                orders[order_id]["items"] = {}
            item_id = item["product id"]
            item["product name"] = re.sub(r"  +", " ", item["product name"])
            del item["product id"]
            orders[order_id]["items"][item_id] = item
        return orders

    def command_scrape(self):
        if not self.can_read(self.ORDERS_CSV):
            self.usage()
            raise IOError("Could not find order_history.csv")
        if not self.can_read(self.ITEMS_CSV):
            self.usage()
            raise IOError("Could not find products_history.csv")

        orders = self.combine_orders_items(self.parse_order_csv())
        self.browser_save_item_info(orders)
        for order_id, order in orders.items():
            order_json_filename = self.part_to_filename(
                PagePart.ORDER_DETAILS, order_id=order_id, ext="json"
            )
            self.write(order_json_filename, {order_id: order}, to_json=True)

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with ../schema.json,
         and a .zip with all attachements
        """

        structure = self.get_structure(
            self.name,
            None,
            (
                "https://www.adafruit.com/index.php"
                "?main_page=account_history_info&order_id={order_id}"
            ),
            "https://www.adafruit.com/product/{item_id}",
        )

        raw_orders = []
        for filename in self.cache["ORDERS"].glob("*/order.json"):
            with open(filename, encoding="utf-8") as input_file:
                raw_orders.append(json.load(input_file))
        filename_base = self.cache["BASE"]

        for order_id_obj in raw_orders:
            for order_id, order_obj in order_id_obj.items():
                order_object = {
                    "id": order_id,
                    "date": (
                        datetime.fromisoformat((order_obj["date_purchased"]))
                        .date()
                        .isoformat()
                    ),
                    "items": [],
                    "total": {"value": order_obj["total"], "currency": "USD"},
                    "subtotal": {
                        "value": order_obj["subtotal"],
                        "currency": "USD",
                    },
                    "shipping": {"value": order_obj["tax"], "currency": "USD"},
                    "tax": {"value": order_obj["shipping"], "currency": "USD"},
                }
                for item_id, item_data in order_obj["items"].items():
                    assert self.can_read(filename_base / item_data["png"])
                    assert self.can_read(filename_base / item_data["html"])
                    assert self.can_read(filename_base / item_data["pdf"])
                    item_obj = {
                        "id": item_id,
                        "name": item_data["product name"],
                        "quantity": int(item_data["quantity"]),
                        "thumbnail": item_data["png"],
                        "attachements": [
                            {
                                "name": "Item PDF",
                                "path": item_data["pdf"],
                                "comment": "PDF print of item page",
                            },
                            {
                                "name": "Item HTML",
                                "path": item_data["html"],
                                "comment": "HTML Scrape of item page",
                            },
                        ],
                    }
                    del item_data["html"]
                    del item_data["pdf"]
                    del item_data["png"]
                    del item_data["product name"]
                    del item_data["quantity"]

                    item_obj.update(item_data)
                    order_object["items"].append(item_obj)

                # Not deleting order_obj['date_purchased'] because it
                # contains more data than we save in "date"
                del order_obj["total"]
                del order_obj["subtotal"]
                del order_obj["tax"]
                del order_obj["shipping"]

                del order_obj["items"]
                # Add all remaning keys to the new object
                order_object.update(order_obj)

                structure["orders"].append(order_object)

        self.output_schema_json(structure)

    def browser_save_item_info(self, orders):
        max_items = settings.ADA_ITEMS_MAX + 1
        counter = 0
        for order_id, order in orders.items():
            self.log.info("Working on order %s", order_id)
            order_dir = self.cache["ORDERS"] / order_id
            self.makedir(order_dir)
            for item_id, item in order["items"].items():
                self.log.debug("Parsing item id %s", item_id)
                counter += 1
                if settings.ADA_ITEMS and item_id not in settings.ADA_ITEMS:
                    self.log.debug(
                        "Skipping item id %s because it is not in ADA_ITEMS",
                        item_id,
                    )
                    continue
                if max_items > 0:
                    if counter == max_items:
                        self.log.debug(
                            "Stopping after %s items",
                            settings.ADA_ITEMS_MAX,
                        )
                        continue
                    elif counter > max_items:
                        continue
                item_url = self.ITEM_URL_TEMPLATE.format(item_id=item_id)
                self.log.debug("Visiting item url %s", item_url)

                pdf_filename = self.part_to_filename(
                    PagePart.ORDER_ITEM,
                    order_id=order_id,
                    item_id=item_id,
                    ext="pdf",
                )
                item["pdf"] = str(
                    Path(pdf_filename).relative_to(self.cache["BASE"])
                )
                html_filename = self.part_to_filename(
                    PagePart.ORDER_ITEM,
                    order_id=order_id,
                    item_id=item_id,
                    ext="html",
                )
                item["html"] = str(
                    Path(html_filename).relative_to(self.cache["BASE"])
                )
                png_filename = self.part_to_filename(
                    PagePart.ORDER_ITEM,
                    order_id=order_id,
                    item_id=item_id,
                    ext="png",
                )
                item["png"] = str(
                    Path(png_filename).relative_to(self.cache["BASE"])
                )
                if (
                    self.can_read(pdf_filename)
                    and self.can_read(html_filename)
                    and self.can_read(png_filename)
                ):
                    self.log.debug(
                        "PDF, HTML and PNG found, will not rescrape."
                    )
                    continue

                self.browser = self.browser_visit_page(item_url)

                item["removed"] = "Page Not Found" in self.browser.title
                if item["removed"]:
                    del item["pdf"]
                    del item["html"]
                    del item["png"]
                else:
                    self.browser_redesign_page()

                    self.browser_cleanup_page(
                        css_selectors=[
                            "div.header-wrap",
                            "nav.breadcrumbs",
                            "footer#siteFooter",
                            "div.instant-search-container",
                            "div.parts_last_bought",
                            "section#related-products",
                            "section#distributors",
                            "section#learndiv",
                            "#___ratingbadge_0",
                            # "div.gallery-thumbnails",
                            "div#prod-rightnav",
                            "div#prod-stock",
                            "div#prod-stock-mobile",
                            "div.gallery-arrow",
                            "div.messages-container" # UPS warning
                        ],
                        # element_tuples=[(By.TAG_NAME, "iframe")],
                    )

                    self.log.debug("Writing thumb to %s", png_filename)
                    counter = 0
                    while True:
                        thumb = self.find_element(
                            By.CSS_SELECTOR, f"div#gallery-slide-{counter}"
                        )
                        if (
                            not thumb
                            or int(thumb.get_attribute("tabindex")) < 0
                        ):
                            self.log.debug(
                                "Did not find %s, trying next",
                                f"div#gallery-slide-{counter}",
                            )
                            counter += 1
                            continue
                        else:
                            break

                    self.write(
                        png_filename,
                        thumb.screenshot_as_base64,
                        from_base64=True,
                        binary=True,
                    )

                    self.remove(self.cache["PDF_TEMP_FILENAME"])
                    self.browser.execute_script("window.print();")
                    self.wait_for_stable_file(self.cache["PDF_TEMP_FILENAME"])

                    self.move_file(
                        self.cache["PDF_TEMP_FILENAME"], pdf_filename
                    )

                    self.write(
                        html_filename, self.browser.page_source, html=True
                    )

    def browser_redesign_page(self) -> None:
        brws = self.browser

        guide_link: WebElement = self.find_element(
            By.CSS_SELECTOR, "a.all-guides-link"
        )
        guide_links_tuple: Dict[str, str] = {}
        for guide in self.find_elements(
            By.CSS_SELECTOR,
            "div.product-info-tutorial div.product-info-tutorials-text",
        ):
            title: WebElement = guide.find_element(
                By.CSS_SELECTOR, " div.product-info-added-tutorial-title a"
            )
            tagline: WebElement = guide.find_element(
                By.CSS_SELECTOR, "div.product-info-tutorials-tagline"
            )
            guide_links_tuple[title.get_attribute("href")] = (
                title.text + ". " + tagline.text
            )

        if guide_link:
            order_handle = brws.current_window_handle
            href = guide_link.get_attribute("href")
            brws.switch_to.new_window()
            brws.get(href)
            guide_links: List[WebElement] = self.find_elements(
                By.CSS_SELECTOR, "a.title"
            )
            for link in guide_links:
                if link.get_attribute("href") not in guide_links_tuple:
                    guide_links_tuple[link.get_attribute("href")] = link.text

            brws.close()
            brws.switch_to.window(order_handle)
        guide_links_tuple = [
            (text, href) for href, text in guide_links_tuple.items()
        ]

        self.log.debug("Preload slides for all images, return to first")
        img_buttons: List[WebElement] = self.find_elements(
            By.CSS_SELECTOR, "button.gallery-thumbnail.indicator-image"
        )
        if img_buttons:
            for img_button in img_buttons:
                img_button.click()
                time.sleep(0.5)
            img_buttons[0].click()

        brws.execute_script(
            """
                // Adafruit has some THICK margins when printing
                let s = document.createElement('style');
                s.type = "text/css";
                s.innerHTML = `
                    @page {
                        margin: .5cm
                    }
                    `;
                s.media = "print";
                document.head.appendChild(s);

                // Funny fonts block text-selection in PDF
                document.querySelectorAll('*')\
                .forEach(function(e){
                    e.style.fontFamily = "sans-serif";
                });

                main_div = document.querySelector("iframe");
                main_div.style.marginLeft = "0";
                main_div.style.marginRight = "0";
                main_div.style.paddingTop = "0";
                document.querySelectorAll('.container')\
                .forEach(function(e){
                    e.style.maxWidth = "unset";
                })
             
                document.querySelectorAll("button.gallery-thumbnail")\
                .forEach(function(e){
                    e.style.background = "unset";
                    e.style.border = "unset";
                })
                let div_learn = document.querySelector("div#tab-learn-content")
                if (div_learn) {
                    while (div_learn.firstChild) {
                        div_learn.removeChild(div_learn.lastChild);
                    }
                    let ul = document.createElement("ul");
                    arguments[0].forEach(function(e){
                        let li = document.createElement("li");
                        let a = document.createElement("a");
                        a.href = e[1];
                        a.appendChild(document.createTextNode(e[0]));
                        li.appendChild(a);
                        ul.appendChild(li);
                    })
                    div_learn.appendChild(ul);
                }

                // Make link to text + url
                document.querySelectorAll('a')\
                .forEach(function(e){
                    url = e.href;
                    text = e.textContent;
                    e.parentNode.replaceChild(
                        document.createTextNode("[" + text + "](" + url + ")"),
                        e
                        );
                })

                // Convert Youtube video players
                // to image and link
                document.querySelectorAll("div.fluid-width-video-wrapper")\
                .forEach(function(e){
                    ifrm = e.querySelector("iframe");
                    url = ifrm.src.replace("embed/","");
                    title = ifrm.title;
                    // Delete all children
                    while (e.firstChild) {
                        e.removeChild(e.lastChild);
                    }
                    let img = document.createElement("img");
                    let p = document.createElement("p");
                    img.src = "https://www.gstatic.com/youtube/" 
                      + "img/branding/favicon/favicon_144x144.png";
                    img.style.height = "4em";
                    img.style.marginRight = "1em";
                    p.appendChild(img);
                    p.appendChild(document.createTextNode("["+ title +"](" + url+ ")"));
                    e.appendChild(p);
                    e.className = "";
                    e.style = "";
                });

                // Append all previously preloaded images to bottom of page
                document.querySelectorAll("div.gallery-slide img")\
                .forEach(function(e){
                    let img = document.createElement("img");
                    let div = document.createElement("div");
                    img.src = e.src;
                    img.style.width="90%";
                    div.style.pageBreakInside = "avoid";
                    div.style.margin = "auto";
                    div.appendChild(img);
                    document.body.appendChild(div);
                });
                document.querySelector("div.gallery-thumbnails").remove()
                """,
            guide_links_tuple,
        )
        time.sleep(2)

    def browser_detect_handle_interrupt(self, expected_url):
        pass

    def browser_login(self, _):
        return False

    def part_to_filename(self, part: PagePart, **kwargs):
        template: str
        if part == PagePart.ORDER_DETAILS:
            template = self.ORDER_FILENAME_TEMPLATE
        elif part == PagePart.ORDER_ITEM:
            template = self.ORDER_ITEM_FILENAME_TEMPLATE
        return Path(template.format(**kwargs))

    def setup_templates(self):
        # pylint: disable=invalid-name
        self.ORDERS_CSV = self.cache["BASE"] / "order_history.csv"
        self.ITEMS_CSV = self.cache["BASE"] / "products_history.csv"
        self.ITEM_URL_TEMPLATE = "https://www.adafruit.com/product/{item_id}"
        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/order.{ext}")
        )
        self.ORDER_ITEM_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/item-{item_id}.{ext}")
        )
