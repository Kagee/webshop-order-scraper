# pylint: disable=unused-import
import base64
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List

from lxml.etree import tostring
from lxml.html import HtmlElement
from lxml.html.soupparser import fromstring
from selenium.common.exceptions import (
    ElementClickInterceptedException,
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


class KjellScraper(BaseScraper):
    tla: Final[str] = "KJL"
    name: Final[str] = "Kjell.com"
    COUNTRY: Final[str] = "test"
    simple_name: Final[str] = "kjell.com-test"


    # Methods that use Selenium to scrape webpages in a browser

    def browser_save_item_thumbnail(self):
        pass

    def browser_cleanup_item_page(self) -> None:
        brws = self.browser_get_instance()
        self.log.debug("Hide fluff, ads, etc")
        elemets_to_hide: List[WebElement] = []

        for element_xpath in [
            # Top three navn divs including breadcrumbs
            '//div[@id="content-container"]/div[3]',
            '//div[@id="content-container"]/div[2]',
            '//div[@id="content-container"]/div[1]',
            # Some not interresting fold-outs
            '//span[contains(text(),"Kundeanmeldelser")]/ancestor::button/parent::div',
            '//span[contains(text(),"Sendinger")]/ancestor::button/parent::div',
            '//span[contains(text(),"Passer bl.a. til")]/ancestor::button/parent::div',
            '//span[contains(text(),"360")]/ancestor::button/parent::div',
            '//span[contains(text(),"Kompletter kjøpet ditt")]/ancestor::button/parent::div',
            '//span[contains(text(),"Alltid trygt å handle hos Kjell")]/parent::div/parent::div/parent::div/parent::div',
            # Warehouse stock info
            '//h4[contains(text(),"Lagerstatus nett og i butikk")]/parent::div/parent::div/parent::div/parent::div',
            # Live-stream video
            '//img[contains(@src,"liveshopping.bambuser.com")]/parent::div/parent::div',
            # 360 images
            '//img[contains(@src,"360images")]/parent::div/parent::div',
            # Add to cart and likes
            '//button[@data-test-id="add-to-shopping-list-button"]/parent::div',
            # Simmilar products
            '//h4[contains(text(),"Lignende produkter")]/parent::div/parent::div',
            '//h3[contains(text(),"Fri standardfrakt")]/parent::div/parent::div/parent::div/parent::div',
            '//h3[contains(text(),"Går bra med")]/parent::div/parent::div/parent::div/parent::div/parent::div'
        ]:
            elemets_to_hide += brws.find_elements(By.XPATH, element_xpath)

        for element_id in [
            # Chat / reviews
            "imbox-launcher-container1900",
        ]:
            elemets_to_hide += brws.find_elements(By.ID, element_id)

        for css_selector in [
            #"div.a-carousel-container",
        ]:
            elemets_to_hide += brws.find_elements(By.CSS_SELECTOR, css_selector)

        for element in [
            #(By.TAG_NAME, "hr"),
            (By.TAG_NAME, "iframe"),
        ]:
            elemets_to_hide += brws.find_elements(element[0], element[1])

        large_images = brws.find_elements(By.XPATH, '//img[contains(@intrinsicsize,"960")]')
        thumbs_div = brws.find_element(By.XPATH, '(//img[contains(@intrinsicsize,"320")])[1]/parent::span/parent::div/parent::div')
        content_container = brws.find_element(By.CSS_SELECTOR, 'div#content-container')

        brws.execute_script(
            """
                // remove spam/ad elements
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].remove()
                }

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

                arguments[2].style.display="block";
                var div = document.createElement('div');
                // large_images
                for (let i = 0; i < arguments[1].length; i++) {
                    var div2 = document.createElement('p');
                    div2.style.breakInside="avoid";
                    var img = document.createElement('img');
                    img.style.display="block";
                    img.style.breakInside="avoid";
                    img.style.width="960px";
                    new_url = new URL(arguments[1][i].src);
                    // some images become TIFF if we delete w/h ...
                    //new_url.searchParams.delete("w");
                    //new_url.searchParams.delete("h");
                    //new_url.searchParams.delete("pad");
                   //new_url.searchParams.delete("ref");
                    img.src = new_url.toString();
                    console.log(img.src)
                    div2.appendChild(img);
                    div.appendChild(div2);
                }
                document.body.appendChild(div);
                arguments[3].style.display="none";
                """,
            elemets_to_hide,
            large_images,
            content_container,
            thumbs_div,
        )
        
        figures = brws.find_elements(By.TAG_NAME, "figure")
        for figure in figures:
            time.sleep(0.5)
            brws.execute_script(
            """
                arguments[0].scrollIntoView();
            """
               , figure)
        time.sleep(2)

    def browser_load_order_list(self):
        if self.options.use_cached_orderlist:
            if self.can_read(self.ORDER_LIST_JSON_FILENAME):
                return self.read(self.ORDER_LIST_JSON_FILENAME, from_json=True)
            else:
                self.log.info("Could not find cached orderlist.")

        brws = self.browser_visit_page(
            self.ORDER_LIST_URL, default_login_detect=False
        )
        time.sleep(2)
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.log.info(
                AMBER(
                    "Please log in to Kjell.com, and press <ENTER> when"
                    " ready..."
                )
            )
            input()
        self.browser_visit_page(self.ORDER_LIST_URL)

        try:
            cookie_accept = brws.find_element(
                By.XPATH,
                "//h4[contains(text(),'"
                " cookies')]/parent::div/div/button/span[contains(text(),"
                " 'Godta')]",
            )
            if cookie_accept:
                cookie_accept.click()
        except NoSuchElementException:
            pass
        transactions = self.browser.execute_script("""
            return window.CURRENT_PAGE.transactions;
            """)
        self.write(self.ORDER_LIST_JSON_FILENAME, transactions, to_json=True)
        return transactions

    # Random utility functions

    @classmethod
    def check_country(cls, country: str):
        country = country.lower()
        if country not in ["no", "se"]:
            raise NotImplementedError("Only supports Kjell.com/[no/se]")
        return country

    def setup_templates(self):
        # pylint: disable=invalid-name
        # URL Templates
        self.ORDER_LIST_URL: str = {
            "no": "https://www.kjell.com/no/mine-sider/mine-kjop"
        }[self.COUNTRY]
        self.LOGIN_PAGE_RE: str = r"https://www.kjell.com.*login=required.*"

        # pylint: disable=invalid-name
        # self.SNAPSHOT_FILENAME_TEMPLATE = str(
        #    self.cache["ORDERS"] / "{order_id}/item-snapshot-{item_id}.{ext}"
        # )
        # self.THUMB_FILENAME_TEMPLATE = str(
        #    self.cache["ORDERS"] / "{order_id}/item-thumb-{item_id}.png"
        # )
        # self.ORDER_FILENAME_TEMPLATE = str(
        #    self.cache["ORDERS"] / "{order_id}/order.{ext}"
        # )
        # self.TRACKING_HTML_FILENAME_TEMPLATE = str(
        #    self.cache["ORDERS"] / "{order_id}/tracking.html"
        # )
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
            orders = self.browser_load_order_list()
            products = {}
            code_len_max = 0
            code_len_min = 9999
            for pli in orders["productListItems"]:
                if pli["code"] not in products:
                    code_len_max = max(code_len_max, len(pli["code"]))
                    code_len_min = min(code_len_min, len(pli["code"]))
                    products[pli["code"]] = pli
                else:
                    raise NotImplementedError("Not implemented: Product code appeared twice")
            self.log.debug("Item code was from %s to %s chars", code_len_min, code_len_max)
            order_dict = {}
            for order in orders["items"]:
                #self.pprint(order)
                order_dict[order['transactionNumber']] = order
                continue
                for line_item in order['lineItems']:
                    # Item codes are in general 5 numders. Below that is bags etc.
                    if line_item["code"] not in products:
                        if len(line_item["code"]) > 4:
                            self.log.debug(f"Product code {line_item['code']} missing")
                        #else:
                        #    self.log.debug(f"Product code {line_item['code']} missing, but probably bag, etc")
            order = order_dict["7707669"]
            #self.pprint(order)
            for line_item in order['lineItems']:
                    # Item codes are in general 5 numders. Below that is bags etc.
                    if line_item["code"] == "90285":
                        self.pprint(line_item)
                        brws = self.browser_visit_page_v2("https://kjell.com" + line_item["url"])
                        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                        time.sleep(2)
                        brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                        self.browser_cleanup_item_page()
                        input()
                    else:
                        self.pprint(line_item["code"] )
            
            # https://archive.org/wayback/available?url=https://www.kjell.com/no/produkter/data/mac-tilbehor/satechi-usb-c-hub-og-minnekortleser-solv-p65027
            # {"url": "https://www.kjell.com/no/produkter/data/mac-tilbehor/satechi-usb-c-hub-og-minnekortleser-solv-p65027", "archived_snapshots": {"closest": {"status": "200", "available": true, "url": "http://web.archive.org/web/20211202101519/https://www.kjell.com/no/produkter/data/mac-tilbehor/satechi-usb-c-hub-og-minnekortleser-solv-p65027", "timestamp": "20211202101519"}}}
            # orders = self.lxml_parse_orderlist_html(order_list_html)
            # self.get_individual_order_details(orders)
        except NoSuchWindowException:
            pass
        self.browser_safe_quit()

    # Class init
    def __init__(self, options: Dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        self.COUNTRY = self.check_country(options.country)
        self.simple_name = "kjell.com-" + self.COUNTRY
        super().setup_cache(Path("kjell-" + self.COUNTRY))
        self.setup_templates()
        self.log.debug(self.ORDER_LIST_URL)