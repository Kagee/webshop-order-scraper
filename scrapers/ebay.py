import re
import time
from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from . import settings
from .base import BaseScraper, PagePart
from .utils import *


class EbayScraper(BaseScraper):
    # Scrape comand and __init__
    name = "eBay"
    tla = "EBY"

    def command_scrape(self):
        order_ids = self.load_or_scrape_order_ids()

        counter = 0
        if self.browser:
            self.browser_safe_quit()
        self.browser_go_to_order_list("classic")
        order_data = {}
        for order_id in order_ids:
            if (
                settings.EBY_ORDERS_MAX > 0
                and counter == settings.EBY_ORDERS_MAX
            ):
                break
            is_old_style_order_id = True
            if isinstance(order_id, list):
                # Old style transid, itemid order data
                order_url = self.ORDER_URL_TEMPLATE_TRANS.format(
                    order_trans_id=order_id[0], order_item_id=order_id[1],
                )
                key = f"{order_id[0]}-{order_id[1]}"
            elif isinstance(order_id, str):
                # New style orderid order data
                is_old_style_order_id = False
                order_url = self.ORDER_URL_TEMPLATE.format(order_id=order_id)
                key = order_id

            order_html_filename = self.ORDER_FILENAME_TEMPLATE.format(
                key=key, ext="html",
            )
            order_json_filename = self.ORDER_FILENAME_TEMPLATE.format(
                key=key, ext="json",
            )

            if settings.EBY_ORDERS and key not in settings.EBY_ORDERS:
                self.log.debug("Not in allowlist: %s", key)
                continue
            if (
                len(settings.EBY_ORDERS_SKIP)
                and key in settings.EBY_ORDERS_SKIP
            ):
                self.log.debug("Not in blocklist: %s", key)
                continue
            counter += 1
            # if not is_old_style_order_id:
            #    continue
            if not self.browser:
                self.browser_go_to_order_list()
                self.browser_website_switch_mode("classic")

            self.log.debug("Visiting %s", order_url)
            self.browser_visit_page_v2(order_url)
            for order_box in self.find_elements(
                By.CSS_SELECTOR, "div.order-box",
            ):
                section_data_items = order_box.find_element(
                    By.CSS_SELECTOR, "div.order-info div.section-data-items",
                )
                shipment_info = order_box.find_element(
                    By.CSS_SELECTOR, "div.shipment-info",
                )
                # div.delivery-address-text => text
                # div.payment-instruments
                #     div.payment-instrument-description -> text?
                #     div. payment-instrument-top => US$
                #     div.payment-instrument-subtext -> date?
                #!!!! div.payment-line-item div.eui-label-value-line )> dt/dd => text
                # div.order-summary > dt/dd => text
                # div.order-foot-notes -> p -> text (not "Learn more")
                order_info_items = {}
                for value_line in section_data_items.find_elements(
                    By.CSS_SELECTOR, "div.eui-label-value-line",
                ):
                    value_name = value_line.find_element(
                        By.CSS_SELECTOR, "dt span.SECONDARY",
                    ).text.strip()
                    if value_name == "Sold by":
                        value = value_line.find_element(
                            By.CSS_SELECTOR, "dd span.PSEUDOLINK",
                        ).text.strip()
                    else:
                        value = value_line.find_element(
                            By.CSS_SELECTOR, "dd span.eui-text-span span",
                        ).text.strip()
                    order_info_items[value_name] = value
                # TODO: Bail out early if order id exists
                order_number = order_info_items["Order number"]
                del order_info_items["Order number"]
                order_data[order_number] = order_info_items
                if "items" not in order_data[order_number]:
                    order_data[order_number]["items"] = {}
                for item in shipment_info.find_elements(
                    By.CSS_SELECTOR,
                    "div.item-card-container div.card-content-box",
                ):
                    # TODO: Order can have multiple items with same id, uniuqe sku
                    item_a: WebElement = item.find_element(
                        By.CSS_SELECTOR, "div.item-description a",
                    ).get_attribute("href")
                    item_id = re.match(r".*itm/([0-9]+).*", item_a).group(1)
                    thumbnail: WebElement = item.find_element(
                        By.CSS_SELECTOR, "div.card-content-image-box img",
                    )
                    thumbnail_src: str = thumbnail.get_attribute("src")
                    name: str = item.find_element(
                        By.CSS_SELECTOR, "p.item-title span.eui-text-span",
                    ).text.strip()
                    price: str = item.find_element(
                        By.CSS_SELECTOR, "p.item-price span.clipped",
                    ).text.strip()
                    # order_data[order_number]["items"]["yellow color"]
                    # order_data[order_number]["items"][""] = no sku
                    order_data[order_number]["items"][item_id] = {
                        "thumbnail": thumbnail_src,
                        "name": name,
                        "price": price,
                    }

            self.pprint(order_data)
            input("enter plz")
        self.pprint(order_data)

        # if not self.can_read(order_html_filename):
        #    self.log.debug("Visiting order URL %s", order_url)
        # else:
        #    self.log.debug(
        #        "Found HTML cache for %s: %s", key, order_html_filename
        #    )
        # if not self.can_read(order_json_filename):
        #    self.log.debug("DO MAKE JSOM PLZ %s", key)
        # else:
        #    self.log.debug(
        #        "Found HTML cache for %s: %s", key, order_html_filename
        #    )

        # self.pprint(order_ids)

    def __init__(self, options: dict):
        super().__init__(options, __name__)
        self.setup_cache("ebay")
        self.setup_templates()
        self.load_imap()
        self.browser = None
        # pylint: disable=invalid-name
        self.WEBSITE_MODE = ""

    def command_db_to_csv(self):
        pass

    def command_load_to_db(self):
        pass

    def load_or_scrape_order_ids(self):
        order_ids = []
        json_filename = self.cache["ORDER_LISTS"] / "order-list.json"
        if not self.options.use_cached_orderlist or not self.can_read(
            json_filename,
        ):
            # We do not want to use cached orderlist
            # Or there is no cached orderlist
            if not self.browser:
                self.browser_go_to_order_list()

            time.sleep(3)
            while True:
                order_ids += self.browser_scrape_individual_order_list()
                next_link = self.find_element(
                    By.CSS_SELECTOR, "a.m-pagination-simple-next",
                )
                if next_link.get_attribute("aria-disabled") == "true":
                    self.log.debug("No more orders")
                    break
                next_link.click()
                self.rand_sleep(2, 4)
            self.log.info(
                "Loaded %s new style order ids from eBay.com", len(order_ids),
            )
            self.log.debug(
                "Writing order list to %s/%s",
                json_filename.parent.name,
                json_filename.name,
            )
            self.write(json_filename, order_ids, to_json=True)
        else:
            self.log.info(
                "Reading order list from %s/%s",
                json_filename.parent.name,
                json_filename.name,
            )
            order_ids = self.read(json_filename, from_json=True)
            self.log.info(
                "Loaded %s new style order ids from json", len(order_ids),
            )

        order_ids += self.IMAP_DATA
        return order_ids

    # LXML-heavy functions
    # ...

    # Selenium-heavy function
    def browser_go_to_order_list(self, mode="mobile"):
        browser_kwargs = {}
        if mode == "mobile":
            browser_kwargs = {
                "change_ua": (
                    "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U)"
                    " AppleWebKit/537.36 (KHTML, like Gecko)"
                    " SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile"
                    " Safari/537.36"
                ),
            }
        if settings.EBY_MANUAL_LOGIN:
            self.log.debug(
                RED("Please log in to eBay and press enter when ready."),
            )
            input()
            brws = self.browser_get_instance(**browser_kwargs)
        else:
            brws = self.browser_get_instance(**browser_kwargs)
            self.browser_website_switch_mode(mode)
            brws.execute_script("window.scrollTo(0,document.body.scrollHeight)")

            self.log.debug("Visiting homepage %s", self.ORDER_LIST_URL)
            self.browser_visit_page_v2(self.ORDER_LIST_URL)
        return brws

    def browser_scrape_individual_order_list(self):
        order_ids = []
        for item_container in self.find_elements(
            By.CSS_SELECTOR, "div.m-mweb-item-container",
        ):
            order_href = self.find_element(
                By.CSS_SELECTOR, "a.m-mweb-item-link", item_container,
            ).get_attribute("href")
            re_matches = re.match(
                r".*\?orderId=(?P<order_id>[0-9-]*).*", order_href,
            )
            order_id = re_matches.group("order_id")
            self.log.debug("Found order id %s", order_id)
            order_ids.append(order_id)
        return order_ids

    def browser_detect_handle_interrupt(self, expected_url):
        time.sleep(2)
        gdpr_accept = self.find_element(
            By.CSS_SELECTOR, "button#gdpr-banner-accept",
        )
        if gdpr_accept:
            self.log.debug("Accepting GDPR/cookies")
            gdpr_accept.click()
            time.sleep(0.5)

        if re.match(r".*captcha.*", self.browser.current_url):
            if self.find_element(By.CSS_SELECTOR, "div#captcha_loading"):
                self.log.info(
                    AMBER("Please complete captcha and press enter: ..."),
                )
                input()
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.browser_login(expected_url)

    def browser_login(self, _):
        """
        Uses Selenium to log in.
        """
        brws, username_data, password_data = self.browser_setup_login_values()

        if username_data and password_data:
            wait = WebDriverWait(brws, 10)

            def captcha_test():
                if self.find_element(By.CSS_SELECTOR, "div#captcha_loading"):
                    self.log.info("Please complete captcha and press enter.")
                    input()

            try:
                self.rand_sleep(0, 2)
                captcha_test()
                css_sel = "input#userid"
                self.log.debug("Looking for %s", css_sel)
                username = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_sel)),
                    "Could not find " + css_sel,
                )
                captcha_test()
                username.click()
                username.send_keys(username_data)
                self.rand_sleep(0, 2)
                captcha_test()
                css_sel = "button#signin-continue-btn"
                self.log.debug("Looking for %s", css_sel)
                wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, css_sel)),
                    "Could not find " + css_sel,
                ).click()
                self.rand_sleep(0, 2)

                captcha_test()
                css_sel = "input#pass"
                self.log.debug("Looking for %s", css_sel)
                password = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css_sel)),
                    "Could not find " + css_sel,
                )
                self.rand_sleep(2, 2)
                captcha_test()
                password.click()
                password.send_keys(password_data)
                self.rand_sleep(0, 2)

                self.log.debug("Looking for %s", "button#sgnBt")
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "button#sgnBt"),
                    ),
                    "Could not find button#sgnBt",
                ).click()
                self.rand_sleep(0, 2)
                captcha_test()
            except TimeoutException as toe:
                # self.browser_safe_quit()
                raise RuntimeError(
                    "Login to eBay was not successful "
                    "because we could not find a expected element..",
                ) from toe
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            self.log.debug(
                "Login to eBay was not successful. If you want continue,"
                " complete login, and then press enter. Press Ctrl-Z to cancel.",
            )
            input()
        self.log.info(GREEN("Login to eBay was successful."))

    def browser_website_switch_mode(self, switch_to_mode=None):
        if switch_to_mode == self.WEBSITE_MODE:
            return

        if self.browser.current_url != self.HOMEPAGE:
            self.log.debug("Going to homepage to switch website mode")
            self.browser.get(self.HOMEPAGE)
        to_mobile_link = self.find_element(By.CSS_SELECTOR, "a#mobileCTALink")
        to_classic_link = self.find_element(
            By.CSS_SELECTOR, "div.gh-mwebfooter__siteswitch a",
        )
        changed = False
        if switch_to_mode == "mobile" and to_mobile_link:
            to_mobile_link.click()
            changed = True
        elif switch_to_mode == "classic" and to_classic_link:
            to_classic_link.click()
            changed = True
        elif not to_mobile_link and not to_classic_link:
            if switch_to_mode != "classic":
                self.log.debug("Failed to find a mode change link!!")
                raise CommandError("Failed to find a mode change link!!")
        self.WEBSITE_MODE = switch_to_mode
        self.log.debug(
            "Switching to %s: %s",
            switch_to_mode,
            "Had to switch" if changed else "Was where we wanted",
        )

    # Utility functions
    def setup_templates(self):
        # pylint: disable=invalid-name
        login_url = re.escape("https://signin.ebay.com")
        self.HOMEPAGE = "https://ebay.com"
        self.LOGIN_PAGE_RE = rf"{login_url}.*"
        self.ORDER_LIST_URL = "https://www.ebay.com/mye/myebay/purchase"
        self.ORDER_LIST_URLv2 = "https://www.ebay.com/mye/myebay/v2/purchase"
        self.ITEM_URL_TEMPLATE = "https://www.ebay.com/itm/{item_id}"

        self.ORDER_URL_TEMPLATE_TRANS = (
            "https://order.ebay.com/ord/show?"
            "transid={order_trans_id}&itemid={order_item_id}#/"
        )
        self.ORDER_URL_TEMPLATE = (
            "https://order.ebay.com/ord/show?orderId={order_id}#/"
        )

        self.ORDER_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{key}/order.{ext}"),
        )
        self.ORDER_ITEM_FILENAME_TEMPLATE: Path = str(
            self.cache["ORDERS"] / Path("{order_id}/item-{item_id}.{ext}"),
        )

    def part_to_filename(self, part: PagePart, **kwargs):
        template: str
        if part == PagePart.ORDER_DETAILS:
            template = self.ORDER_FILENAME_TEMPLATE
        elif part == PagePart.ORDER_ITEM:
            template = self.ORDER_ITEM_FILENAME_TEMPLATE
        return Path(template.format(**kwargs))

    def load_imap(self):
        # pylint: disable=invalid-name
        self.IMAP_DATA = []
        if self.can_read(self.IMAP_JSON):
            self.IMAP_DATA = self.read(self.IMAP_JSON, from_json=True)
            self.log.debug(
                "Loaded %s old style order ids from IMAP data",
                len(self.IMAP_DATA),
            )

    def setup_cache(self, base_folder: Path):
        super().setup_cache(base_folder)
        # pylint: disable=invalid-name
        self.IMAP_JSON = Path(settings.CACHE_BASE, "imap", "imap-ebay.json")
