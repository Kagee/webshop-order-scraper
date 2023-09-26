# pylint: disable=unused-import
import base64
from decimal import Decimal
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Union
from urllib.parse import urlparse, urlencode, parse_qs
import requests
import filetype

from selenium.common.exceptions import (
    NoSuchElementException,
    NoSuchWindowException,
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
            if self.options.use_cached_orderlist and self.can_read(
                self.ORDER_LIST_JSON
            ):
                order_dict = self.read(self.ORDER_LIST_JSON, from_json=True)
            else:
                order_dict = {}
                brws = self.browser_visit("https://www.komplett.no/orders")
                brws.execute_script(
                    "window.scrollTo(0,document.body.scrollHeight)"
                )
                time.sleep(2)
                brws.execute_script(
                    "window.scrollTo(0,document.body.scrollHeight)"
                )
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
                    order_id = order_element.find_element(By.CSS_SELECTOR, "td.order-number").text.strip()
                    order_status = order_element.find_element(By.CSS_SELECTOR, "td.status").text.strip()
                    order_dict[order_id] = {
                        "status": order_status
                    }

                for order_id, order_dict in order_dict.items():
                    if order_id != "200633800":
                        continue
                    # nyeste: 204547164
                    # pc med childitems 204139923
                    # tre items, 200633800
                    # gavekort 203867530
                    # siste: 15478583
                    self.log.debug("Scraping order id %s", order_id)
                    self.browser_visit(
                        f"https://www.komplett.no/orders/{order_id}"
                    )

                     a= """
                        div.order div.order-details div.info-row table (2)
                        caption.text -> "Ordredetaljer" | "Levering"

                        -> tobdy (th|td)
                        -> if a i td ->save pdf auto open close), a.text = name

                        div.order table.products-table tbody tr.table-row

                        if class "child"

                        td.image-col img.src thumb 

                        td.description-col details
                        div.webtext.a -> "/product/1152480?noredirect=true"
                        p.webtext1 -> name from order
                        p.webtext1 -> description
                        p.sku-text -> "Varenr: 1152480 / Prodnr: WIFIDS10WT"

                        td.quantity-container quantity

                        td.price item price

                        td.total -> item total

                        div.order div.product-list-footer table tr -> td class label/price
                        "N vare(r|)" -> item total

                        https://www.komplett.no/product/1122618?noredirect=true
                     """   

                    input()
                    break
        except NotImplementedError as nie:
            self.log.error(str(nie))
            self.browser_safe_quit()

    def _cleanup(self):
        a = """
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
                });


document.querySelectorAll("div.product-section-content").forEach(function(e){
  e.style.display="block";
  e.style.float="unset";
})

document.querySelectorAll("div.product-section-content div").forEach(function(e){
  e.style.float="unset";
})


document.querySelectorAll("figure").forEach(function(e){e.style.pageBreakInside="avoid";})

document.querySelectorAll("button.read-more-toggle").forEach(function(e){e.click()})
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
  e.remove(); // iframe removed

  np = parent;

  for (let i = 0; i < 10; i++) {
    c = np.parentElement.getAttribute("class");
    if (c && (c.toLowerCase().search('video') >= 0)){
      parent = np.parentElement;
    }
    np = np.parentElement;
  }
  parent.innerHTML="";
  p = document.createElement("p");
  p.innerText = video;
  while (parent.lastChild) { parent.lastChild.remove(); }
  parent.appendChild(p);
})
// time.sleep
[
  'videoly-tape'
].forEach((e) => {f=document.querySelector(e); if(f){f.remove()}});

        """

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

    def command_to_std_json(self):
        structure = self.get_structure(
            self.name,
            None,
            "https://www.adafruit.com/index.php"
            "?main_page=account_history_info&order_id={order_id}",
            "https://www.adafruit.com/product/{item_id}",
        )

        self.output_schema_json(structure)

    def setup_templates(self):
        # pylint: disable=invalid-name
        self.ORDER_LIST_JSON = self.cache["BASE"] / "order_list.json"
        self.ORDERS = self.cache["BASE"] / "products_history.csv"
        self.ITEM_URL_TEMPLATE = "https://www.adafruit.com/product/{item_id}"
        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/order.{ext}")
        )
        self.ORDER_ITEM_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/item-{item_id}.{ext}")
        )
