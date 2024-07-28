# ruff: noqa: C901,ERA001,PLR0912,PLR0915
import contextlib
import json
import time
from pathlib import Path
from typing import Final

from selenium.webdriver.common.by import By

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
        order_list = []
        order_ids = set()

        order_list_path = self.cache["ORDER_LISTS"] / "order_list.json"
        if order_list_path.is_file():
            with order_list_path.open() as order_list_file:
                order_list = json.load(order_list_file)
                order_ids = {x["id"] for x in order_list}
                for order_id in order_ids:
                    self.log.debug("Loaded list order id %s", order_id)

        if not self.options.use_cached_orderlist:
            self.log.debug("Downloading order list")
            # We visit this to make sure we are logged inn
            if not self.browser:
                self.browser_visit(
                    "https://www.jula.no/account/mine-innkjop/",
                )
            order_list_json = self.browser_get_json(
                "view-source:https://apigw.jula.no/digital-platform/v1/Customer/order",
            )
            if order_list_json["hasNextPage"]:
                msg = (
                    "Orderlist has hasNextPage=True. "
                    "Don't know how to handle this."
                )
                raise NotImplementedError(msg)
            for order_info in order_list_json["transactions"]:
                if order_info["id"] not in order_ids:
                    self.log.debug("Found new order id: %s", order_info["id"])
                    order_list.append(order_info)
        else:
            self.log.debug("Using cached order list: %s", order_list_path)

        order_ids = {
            x["id"] for x in order_list
        }  # recalculate in case we downloaded any

        with order_list_path.open("w") as order_list_file:
            json.dump(order_list, order_list_file, indent=4)

        orders = {}

        for order_file_path in list(self.cache["ORDERS"].glob("*.json")):
            with order_file_path.open() as order_file:
                order_data = json.load(order_file)
                oid = order_data["transactionHead"]["orderId"]
                self.log.debug("Loaded order data for id %s", oid)
                with contextlib.suppress(KeyError):
                    order_ids.remove(oid)
                orders[oid] = order_data

        for order_id in order_ids:
            # there are order number we have not scraped to disk
            order_data = self.browser_get_json(
                "view-source:https://apigw.jula.no/"
                "digital-platform/v1/Customer/order/" + order_id,
            )
            oid = order_data["transactionHead"]["orderId"]
            self.pprint(order_data)
            self.log.debug("Downloaded order data for id %s", oid)
            with (self.cache["ORDERS"] / (oid + ".json")).open(
                "w",
            ) as order_json_file:
                json.dump(order_data, order_json_file, indent=4)
            orders[oid] = order_data

        for order in orders.values():
            # Cache thumbnails
            oid = order["transactionHead"]["orderId"]
            order_folder: Path = self.cache["ORDERS"] / oid
            order_folder.mkdir(exist_ok=True)
            for line in order["lines"]:
                iid = line["variantId"]
                for format_ in line["mainImage"]["formats"]:
                    if "2048px trimmed transparent" in format_["type"]:
                        line["thumbnail_path"] = (
                            Path(
                                self.find_or_download(
                                    format_["url"]["location"],
                                    f"thumbnail-{iid}-",
                                    order_folder,
                                ),
                            )
                            .relative_to(self.cache["BASE"])
                            .as_posix()
                        )
                        break
                else:
                    self.pprint(order)
                    msg = (
                        "Image with format `2048px trimmed"
                        " transparent` not found for "
                        f"item id {line['variantId']}"
                    )
                    raise NotImplementedError(msg)
                if "url" in line:
                    item_pdf = order_folder / f"item-{iid}.pdf"
                    if item_pdf.is_file():
                        line["pdf_path"] = item_pdf.relative_to(
                            self.cache["BASE"],
                        ).as_posix()
                        continue
                    # nope, we need to make the PDF
                    self.log.debug("We need to scrape %s", line["url"])
                    self.scrape_item_page(line["url"], item_pdf)

    def scrape_item_page(self, url: str, pdf_file: Path) -> None:
        self.browser_visit(url)

        if read_more_btn := self.find_element(
            By.XPATH,
            "//button[starts-with(normalize-space(text()), 'Les mer')]",
        ):
            read_more_btn.click()
            self.log.debug("`Les mer` clicked")

        if tech_spec := self.find_element(
            By.XPATH,
            (
                "//span[starts-with(normalize-space(text()), "
                "'Teknisk spesifikasjon')]/parent::h2/parent::div"
            ),
        ):
            tech_spec.click()
            self.log.debug("`Teknisk spesifikasjon` clicked")

        self.browser.execute_script(
            """
                function rx(xpath) {
                    f = document.evaluate(
                        xpath,
                        document.body,
                        null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE
                        ).singleNodeValue;
                    if (f) {
                        console.log("Removing ", f);
                        f.remove();
                        return true;
                    } else {
                        /* console.log("Failed to remove " + xpath); */
                        return false;
                    }
                };
                document.body.prepend(document.querySelector('h1'));
                [
                    "//videoly-slider//parent::div",
                    "//main/preceding-sibling::div",
                    "//div[contains(@class, '[grid-area:sidebar]')]",
                    "//span[starts-with(normalize-space(text()), 'Anmeldelser')]/parent::h2/parent::div",
                    "//span[starts-with(normalize-space(text()), 'Passer til')]/parent::h2/parent::div",
                    "//div[@id='similar-products']",
                    "//header",
                    "//nav",
                    "//footer",
                ].forEach((e) => {
                    let loop = true;
                    while (loop) {
                        loop = rx(e);
                    }
                });
                document.querySelectorAll("*").forEach(
                    (el) => {
                        el.style.fontFamily = "unset";
                        }
                    );

            """,
        )
        self.log.debug("We did not save %s to %s", url, pdf_file)
        input("Press enter to continue")

        """
            delete:
            a href="#product-reviews" -> parent div -> parent div

        """

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
        self.valid_json(structure)
        # self.output_schema_json(structure)

    # Class init
    def __init__(self, options: dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        # self.COUNTRY = self.check_country(options.country)
        super().setup_cache(self.simple_name)
        self.setup_templates()
