# ruff: noqa: C901,ERA001,PLR0912,PLR0915
import re
import time
from datetime import datetime
from typing import Final

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from .base import BaseScraper


class JulaScraper(BaseScraper):
    tla: Final[str] = "JUL"
    name: Final[str] = "Jula"
    simple_name: Final[str] = "jula"

    # Methods that use Selenium to scrape webpages in a browser

    # Random utility functions
    def setup_templates(self):
        pass
        # self.ORDERS_JSON = self.cache["ORDER_LISTS"] / "orders.json"
        # self.INVOICES_JSON: Path = self.cache["ORDER_LISTS"] / "invoices.json"
        # self.DETAILS_JSON: Path = (
        #    self.cache["ORDER_LISTS"] / "invoiceDetails.json"
        # )

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        # self.log.debug(expected_url)
        time.sleep(5)
        if (
            expected_url == "https://www.jula.no/account/mine-innkjop/"
            and "returnPath" in self.browser.current_url
        ):
            self.log.error("Please log in manually and then press endet")
            input()

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your Kjell orders.
        """
        orders = {}
        brws = self.browser_visit("https://www.jula.no/account/mine-innkjop/")
        "https://www.jula.no/account/mine-innkjop/1796354449/"
        # wait10 = WebDriverWait(brws, 10)  # wait for sometyhing to appear
        order_links: list[WebElement] = brws.find_elements(
            By.XPATH,
            "//a[contains(@href,'account/mine-innkjop')]",
        )

        for order_link in order_links:
            href = order_link.get_dom_attribute("href")
            # self.log.debug(href)
            if m := re.match(r"^.*mine-innkjop\/([0-9]+)\/?$", href):
                orders[m[1]] = {
                    "url": "https://www.jula.no/account/mine-innkjop/" + m[1],
                    "id": m[1],
                    "extra_data": {},
                }
        for order in orders.values():
            self.browser_visit(order["url"])
            time.sleep(3)
            main = brws.find_element(
                By.XPATH,
                "//main//h1/parent::div",
            )
            for x in ["Ordrenummer", "Kjøpsdato"]:
                e = main.find_element(
                    By.XPATH,
                    (
                        ".//p[contains(@class, 'text-base')]"
                        f"[contains(text(), '{x}')]"
                    ),
                )
                if x == "Ordrenummer":
                    order["extra_data"]["non_web_order_number"] = e.text.split(
                        ":",
                    )[1].strip()
                elif x == "Kjøpsdato":
                    order["date"] = (
                        datetime.strptime(
                            e.text.split(":")[1].strip(),
                            "%d.%m.%Y",
                        )
                        .astimezone()
                        .date()
                        .isoformat()
                    )

            articles_div = main.find_elements(
                By.XPATH,
                (".//h2/parent::div//article/div"),
            )
            order["items"] = []
            for art in articles_div:
                item = self.extract_item_data_from_order_page(art)
                self.pprint(item)
                order["items"].append(item)

            shipping = main.find_element(
                By.XPATH,
                (
                    ".//p[starts-with(normalize-space(text()), 'Frakt')]"
                    "/parent::div/descendant::span"
                ),
            )
            order["shipping"] = shipping.text.strip().replace(".-", ",00")
            try:
                discount = main.find_element(
                    By.XPATH,
                    (
                        ".//p[starts-with(normalize-space(text()), 'Rabatt')]"
                        "/parent::div/descendant::span"
                    ),
                )
                order["extra_data"]["discount"] = discount.text.strip().replace(
                    ".-",
                    ",00",
                )
            except NoSuchElementException:
                pass
            total_div = main.find_element(
                By.XPATH,
                (
                    ".//p[starts-with(normalize-space(text()), 'Totalt')]"
                    "/parent::div/descendant::div"
                ),
            )
            ps = total_div.find_elements(
                By.TAG_NAME,
                "p",
            )
            for p in ps:
                t = p.text.strip().replace("\u202f", "")

                if "moms" in p.text:
                    num = re.match(".*moms ([0-9 ,.-]*)$", p.text)[1]
                    num = num.strip().replace(",", ".").replace(".-", ".00")
                    order["tax"] = str(num)
                    # This should work if extract is successfull
                    _test_float_convert = float(order["tax"])
                else:
                    if ".-" in t:
                        t = t.replace(".-", ".00")
                    else:
                        # divide by 100 using strings
                        a = list(t)
                        t = "".join(a[:-2]) + "." + "".join(a[-2:])
                    order["total"] = t
                    # This should work if extract is successfull
                    _test_float_convert = float(order["total"])

            for item in order["items"]:
                self.extract_item_page(item)

            del order["url"]
            # self.pprint(order)
            # input("waiting ... no more code implemented")
            # raise RuntimeError
        # self.pprint(orders)
        raise RuntimeError
        return orders

    def extract_item_page(self, _item: dict) -> dict:
        """
        img_buttons: list[WebElement] = self.find_elements(
            By.CSS_SELECTOR,
            "button.gallery-thumbnail.indicator-image",
        )
        if img_buttons:
            for img_button in img_buttons:
                img_button.click()
                time.sleep(0.5)
            img_buttons[0].click()
        """
        """
        click:
        //button[starts-with(normalize-space(text()), 'Les mer')]
        //span[starts-with(normalize-space(text()), 'Teknisk spesifikasjon')]/parent::h2/parent::div
        """
        """
        document.querySelectorAll("*").forEach(
        (el) => {
            el.style.fontFamily = "unset";
            }
        );
        document.body.prepend(document.querySelector('h1'))
        """
        """
            delete:
            //main/preceding-sibling::div -> many
            //videoly-slider//parent::div -> many
            //div[contains(@class, '[grid-area:sidebar]')]
            header
            nav
            a href="#product-reviews" -> parent div -> parent div
            //span[starts-with(normalize-space(text()), 'Anmeldelser')]/parent::h2/parent::div
            //span[starts-with(normalize-space(text()), 'Passer til')]/parent::h2/parent::div
            div id="similar-products"
            footer
        """

    def extract_item_data_from_order_page(
        self,
        art: WebElement,
    ) -> dict:
        item = {}
        item["img_url"] = re.sub(
            "/w:[0-9]{1,5}/",
            "/",
            art.find_element(By.TAG_NAME, "img")
            .get_dom_attribute(
                "src",
            )
            .replace("/preset:jpgoptimized/", "/"),
        )

        item["price"] = (
            art.find_element(By.XPATH, "./p")
            .text.strip()
            .replace(".-", ".00")
            .replace("\u202f", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        # This should work if extract is successfull
        _test_float_convert = float(item["price"])
        # item may not have URL if not avaliable in webshop (i.e. sodas)
        name = art.find_element(
            By.XPATH,
            ".//div/p[starts-with(@id, 'summary-product-title')]",
        )
        item["name"] = name.text.strip()
        try:
            name.find_element(
                By.XPATH,
                ".//a",
            )
            item["avaliable_on_web"] = True
        except NoSuchElementException:
            self.log.warning("%s it not avaliable on web", item["name"])
            item["avaliable_on_web"] = False

        p_span = art.find_elements(By.XPATH, ".//p/span")
        for span in p_span:
            t = span.text.strip()
            num = re.match(r".*\s([0-9]*)$", t)[1]
            if t.startswith("Antall"):
                item["quantity"] = num
            elif t.startswith("Artikkelnummer"):
                item["id"] = num
        return item

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with schema,
         and a .zip with all attachements
        """
        structure = self.get_structure(
            self.name,
            None,
            "https://www.jula.no/account/mine-innkjop/{order_id}/",
            "https://www.jula.no/catalog/-{item_id}/",
        )
        # scrape_data = self.command_scrape()
        # self.pprint(scrape_data, 260)
        self.valid_json(structure)
        # self.output_schema_json(structure)

    # Class init
    def __init__(self, options: dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        # self.COUNTRY = self.check_country(options.country)
        super().setup_cache(self.simple_name)
        self.setup_templates()
