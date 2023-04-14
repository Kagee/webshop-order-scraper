import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from django.core.files import File

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from ....models.attachement import Attachement
from ....models.order import Order
from ....models.orderitem import OrderItem
from ....models.shop import Shop
from .base import BaseScraper, PagePart


# Scraper for trying out code for other scrapers
class AdafruitScraper(BaseScraper):
    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options, __name__)
        self.setup_cache("adafruit")
        self.setup_templates()

    def command_load_to_db(self):
        if settings.SCRAPER_ADA_DB_SHOP_ID != -1:
            self.log.debug("Using db shop ID from SCRAPER_ADA_DB_SHOP_ID")
            db_shop_id = int(settings.SCRAPER_ADA_DB_ID)
        elif self.options["db_shop_id"] != -1:
            self.log.debug("Using db shop ID from --db-shop-id")
            db_shop_id = int(self.options["db_shop_id"])
        else:
            self.log.debug(
                "No value for db shop ID found, unable to load to db. Need"
                " either SCRAPER_ADA_DB_SHOP_ID or --db-shop-id"
            )
            raise CommandError(
                "No value for db shop ID found, unable to load to db."
            )
        shop = Shop.objects.get(id=db_shop_id)
        self.log.debug("Loaded shop from model: %s", shop)

        self.log.debug("Loading on-disk data")
        for json_file in self.cache["ORDERS"].glob("*/*.json"):
            self.log.debug(
                "Processing file %s/%s", json_file.parent.name, json_file.name
            )
            order_dict = self.read(json_file, from_json=True)

            for order_id, order in order_dict.items():
                items = order["items"].copy()
                del order["items"]
                date = order["date_purchased"]
                del order["date_purchased"]
                self.pprint(items)

                order_object, created = Order.objects.update_or_create(
                    shop=shop,
                    order_id=order_id,
                    defaults={
                        "date": datetime.fromisoformat(date),
                        "extra_data": order,
                    },
                )

                for item_id, item in items.items():
                    # print(item_id, item)
                    name = item["product name"]
                    del item["product name"]

                    quantity = item["quantity"]
                    del item["quantity"]

                    thumb_path = self.cache["BASE"] / item["png"]
                    thumb_img = File(open(thumb_path, "rb"), thumb_path.name)
                    del item["png"]

                    # TODO: Save html and pdf as attachements
                    # del item["html"]
                    # del item["pdf"]

                    item_object, created = OrderItem.objects.update_or_create(
                        order=order_object,
                        item_id=item_id,
                        item_sku="",  # Adafruit has no SKUs?
                        defaults={
                            "name": name,
                            "count": quantity,
                            "extra_data": item,
                        },
                    )

                    if item_object.thumbnail:
                        item_object.thumbnail.delete()
                    item_object.thumbnail = thumb_img
                    item_object.save()

                    if thumb_img:
                        thumb_img.close()
                if created:
                    self.log.debug("Created order %s", order_id)
                else:
                    self.log.debug("Created or updated order %s", order_object)

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
            raise CommandError("Could not find order_history.csv")
        if not self.can_read(self.ITEMS_CSV):
            self.usage()
            raise CommandError("Could not find products_history.csv")

        orders = self.combine_orders_items(self.parse_order_csv())
        self.browser_save_item_info(orders)
        for order_id, order in orders.items():
            order_json_filename = self.part_to_filename(
                PagePart.ORDER_DETAILS, order_id=order_id, ext="json"
            )
            self.write(order_json_filename, {order_id: order}, to_json=True)

    def browser_save_item_info(self, orders):
        max_items = settings.SCRAPER_ADA_ITEMS_MAX + 1
        counter = 0
        for order_id, order in orders.items():
            self.log.info("Working on order %s", order_id)
            order_dir = self.cache["ORDERS"] / order_id
            self.makedir(order_dir)
            for item_id, item in order["items"].items():
                self.log.debug("Parsing item id %s", item_id)
                counter += 1
                if (
                    settings.SCRAPER_ADA_ITEMS
                    and item_id not in settings.SCRAPER_ADA_ITEMS
                ):
                    self.log.debug(
                        (
                            "Skipping item id %s because it is not in"
                            " SCRAPER_ADA_ITEMS"
                        ),
                        item_id,
                    )
                    continue
                if max_items > 0:
                    if counter == max_items:
                        self.log.debug(
                            "Stopping after %s items",
                            settings.SCRAPER_ADA_ITEMS_MAX,
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
                    img.src = "https://www.gstatic.com/youtube/img/branding/favicon/favicon_144x144.png";
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

    def browser_detect_handle_interrupt(self, url):
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
