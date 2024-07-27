# ruff: noqa: C901,ERA001,PLR0912,PLR0915
import re
import time
from datetime import datetime
from typing import Final

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
        self.log.debug(expected_url)
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
                }
        for order_numer, order in orders.items():
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
                        "//p[contains(@class, 'text-base')]"
                        f"[contains(text(), '{x}')]"
                    ),
                )
                if x == "Ordrenummer":
                    order["order_name"] = e.text.split(":")[1].strip()
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

                # //main//h2/parent::div -> Din bestilling
                #   -> //article -> many articles
                #      -> div
                #           -> img
                #           -> div
                #               -> p -> a -> text = Name, href= https://www.jula.no/catalog/.../werther%E2%80%99s-original-cream-candies-027450/
                #               -> p -> span(s) -> Artikkelnummer. / Antall:
                #           -> p '1&nbsp;099.-' / '49,90'

                # //p[starts-with(normalize-space(text()), 'Frakt')]/parent::div/descendant::span -> 0.-
                # //p[starts-with(normalize-space(text()), 'Rabatt')]/parent::div/descendant::span -> −19,38
                # //p[starts-with(normalize-space(text()), 'Totalt')]/parent::div/descendant::div
                #    -> p where text contains moms: "hvorav moms 158,44"
                #    -> else: 795<sup class="top-0 text-[50%] leading-none">70</sup>
                #    -> 2 210<span class="pr-[0.08em] -tracking-[0.125em] -ml-[0.02em]">.-</span>
                #    -> if contains ",-" -> null ore, ellers text -> tall, del på 100
                self.log.debug(e.text)
            # for item in items:
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

            #
            #
            # //p[contains(@class, 'text-base')][contains(text(), 'Ordrenummer')]
            self.pprint(order)
            input("waiting ... no more code implemented")
            raise RuntimeError

        self.pprint(orders)

        raise RuntimeError
        return orders

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
