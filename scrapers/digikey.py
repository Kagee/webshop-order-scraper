# ruff: noqa: C901,ERA001,PLR0912,PLR0915
import json
from datetime import datetime
from pathlib import Path
from typing import Final

from .base import BaseScraper


class DigikeyScraper(BaseScraper):
    tla: Final[str] = "DIG"
    name: Final[str] = "Digikey"
    simple_name: Final[str] = "digikey"

    # Methods that use Selenium to scrape webpages in a browser

    # Random utility functions
    def setup_templates(self):
        self.ORDERS_JSON = self.cache["ORDER_LISTS"] / "orders.json"
        self.INVOICES_JSON: Path = self.cache["ORDER_LISTS"] / "invoices.json"
        self.DETAILS_JSON: Path = (
            self.cache["ORDER_LISTS"] / "invoiceDetails.json"
        )

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        pass

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your Kjell orders.
        """
        input_files = [
            self.ORDERS_JSON,
            self.INVOICES_JSON,
            self.DETAILS_JSON,
        ]
        for x in input_files:
            if not x.is_file():
                self.log.error(
                    "Could not find required inout file %s",
                    x,
                )
                msg = (
                    "Visit https://www.digikey.no/OrderHistory/List to "
                    "download the input files "
                    + ", ".join(y.name for y in input_files)
                    + " and place them in "
                    + str(self.cache["ORDER_LISTS"]),
                )
                self.log.error(msg)
                raise ValueError(msg)

        with (self.cache["ORDER_LISTS"] / "invoices.json").open() as f:
            invoices_json = json.load(f)

        orders: dict[str] = {}
        for invoice in invoices_json:
            order_number = str(invoice["orderNumber"])
            order_folder: Path = self.cache["ORDERS"] / str(order_number)
            order_folder.mkdir(exist_ok=True)

            order = {
                "order_number": order_number,
                "items": [],
                "extra_data": {},
                "folder": order_folder,
                "date": invoice["dateEntered"],
            }
            del invoice["orderNumber"]
            if order_number in orders:
                msg = "orderNumber repeated in invoices.json"
                raise ValueError(msg)

            if len(invoice["invoicePricing"]) > 1:
                msg = "invoicePricing was longer than 1"
                raise ValueError(msg)

            try:
                order["tax"] = invoice["invoicePricing"][0]["salesTax"] / 100
                order["shipping"] = (
                    invoice["invoicePricing"][0]["freightValue"] / 100
                )
                del invoice["invoicePricing"][0]["salesTax"]
                del invoice["invoicePricing"][0]["freightValue"]
            except IndexError:
                order["extra_data"][
                    "webshop-order-scraper-comment-invoicePricing"
                ] = "Order data had no invoicePricing, probably very old order."

            if len(invoice["invoices"]) > 1:
                msg = "invoices was longer than 1"
                raise ValueError(msg)

            order["subtotal"] = invoice["invoices"][0]["orderValue"] / 100
            order["currency"] = invoice["currencyIso"]
            del invoice["invoices"][0]["orderValue"]

            try:
                order["total"] = invoice["invoices"][0]["invoiceTotalPrice"]
                del invoice["invoices"][0]["invoiceTotalPrice"]
            except KeyError:
                order["extra_data"][
                    "webshop-order-scraper-comment-invoiceTotalPrice"
                ] = (
                    "Order data had no invoiceTotalPrice,"
                    " probably very old order."
                )

            # self.pprint(order)
            # order["extra_data"] = invoice
            if order_number in orders:
                msg = "Order number duplicated"
                raise ValueError(msg)
            orders[order_number] = order

        with (self.cache["ORDER_LISTS"] / "invoiceDetails.json").open() as f:
            invoice_details_json = json.load(f)

        for details in invoice_details_json:
            order_number = str(details["orderNumber"])

            if order_number not in orders:
                msg = "Unknow orderNumber"
                raise ValueError(msg)

            if len(details["invoiceDetails"]) > 1:
                msg = "invoiceDetails was longer than 1"
                raise ValueError(msg)
            self.pprint(details["invoiceDetails"])
            i = details["invoiceDetails"][0]

            order_folder: Path = self.cache["ORDERS"] / str(order_number)
            order_folder.mkdir(exist_ok=True)

            order_folder: Path = orders[order_number]["folder"]
            item_folder: Path = order_folder / str(
                i["productId"],
            )
            item_folder.mkdir(exist_ok=True)

            item = {
                "id": str(i["productId"]),
                "subtotal": i["unitPrice"] / 100000,
                "total": i["extendedPrice"] / 100,
                "quantity": i["quantityTotal"],
                "name": ", ".join(
                    [
                        i["description"],
                        i["manufacturerProductNumber"],
                        i["manufacturerName"],
                    ],
                ),
                "item_page": f"https://www.digikey.no/no/products/detail/-/-/{i['productId']}",
                "extra_data": {},
            }

            def get_files(f):
                return set(f.glob("*")) - set(
                    f.glob("thumbnail-*"),
                )

            for file in self.cache["TEMP"].glob("*"):
                self.log.debug("Deleting %s from TEMP dir.", file.name)
                file.unlink(missing_ok=True)
            files = get_files(item_folder)
            skip_gather = False
            if files:
                for f in files:
                    self.log.debug(f.name)
                skip_gather = (
                    True  # we assume files existing means all files downloaded
                )
                # skip_gather = (
                #    input(
                #        f"Found the files above for {item['name']}"
                #        ", skip item data gathering? [Y/n]",
                #    ).upper()
                #    != "Y"
                # )
            if not skip_gather:
                self.log.debug(
                    (
                        "Visit %s, save PDF and attachements to %s, "
                        "and press enter to continue."
                    ),
                    item["item_page"],
                    self.cache["TEMP"],
                )
                while (
                    input(
                        "Press enter to list found files,"
                        " press y then enter to accept\n",
                    ).lower()
                    != "y"
                ):
                    for file in self.cache["TEMP"].glob("*"):
                        if file.name == "temporary.pdf":
                            self.log.debug("Item PDF: %s", file.name)
                        else:
                            self.log.debug("Attachement: %s", file.name)

                for file in self.cache["TEMP"].glob("*"):
                    if file.name == "temporary.pdf":
                        file.rename(item_folder / "attachement-item-scrape.pdf")
                    else:
                        file.rename(item_folder / f"attachement-{file.name}")

            item["attachments"] = get_files(item_folder)

            tbu = i["thumbnailUrl"].replace("//", "https://")
            imu = i["imageUrl"].replace("//", "https://")

            # Fallback to thumbnail image
            item["thumbnail_file"] = self.find_or_download(
                [imu, tbu],
                "thumbnail-",
                item_folder,
            )

            for d in [
                "productId",
                "unitPrice",
                "extendedPrice",
                "quantityTotal",
                "description",
                "manufacturerProductNumber",
                "manufacturerName",
            ]:
                del details["invoiceDetails"][0][d]
            # item["extra_data"] = details
            orders[order_number]["items"].append(item)

        # self.pprint(orders, 260)
        # self.log.debug(self.cache)
        return orders

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with schema,
         and a .zip with all attachements
        """
        structure = self.get_structure(
            self.name,
            None,
            "https://www.digikey.no/OrderHistory/ReviewOrder/{order_id}",
            "https://www.digikey.no/no/products/detail/-/-/{item_id}",
        )
        scrape_data = self.command_scrape()
        self.pprint(scrape_data, 260)
        structure["orders"] = []
        for order_id, scraped_data in scrape_data.items():
            order = {
                "id": str(order_id),
                "items": [],
                "extra_data": scraped_data["extra_data"],
                "date": datetime.fromisoformat(
                    scraped_data["date"].replace("Z", "+00:00"),
                )
                .date()
                .isoformat(),
                # no order attachements scraped
            }
            del scraped_data["date"]
            for unit in [
                "total",
                "tax",
                "subtotal",
                "shipping",
            ]:
                if unit in scraped_data:
                    order[unit] = self.get_value_currency(
                        unit,
                        scraped_data[unit],
                        scraped_data["currency"],
                    )
                    del scraped_data[unit]

            if not len(
                scraped_data["items"],
            ):
                self.log.error("Order id %s has no items, skipping", order_id)
                continue

            for scraped_item in scraped_data["items"]:
                item = {
                    "name": scraped_item["name"],
                    "id": scraped_item["id"],
                    "quantity": scraped_item["quantity"],
                    "extra_data": scraped_item["extra_data"],
                }

                if (
                    "thumbnail_file" in scraped_item
                    and scraped_item["thumbnail_file"]
                ):
                    item["thumbnail"] = (
                        Path(
                            scraped_item["thumbnail_file"],
                        )
                        .relative_to(self.cache["BASE"])
                        .as_posix()
                    )
                    del scraped_item["thumbnail_file"]

                for unit in [
                    "total",
                    "tax",
                    "subtotal",
                    "shipping",
                ]:
                    if unit in scraped_item:
                        order[unit] = self.get_value_currency(
                            unit,
                            scraped_item[unit],
                            scraped_data["currency"],
                        )
                        del scraped_item[unit]
                item["attachements"] = []
                if "attachments" in scraped_item:
                    for attachment in scraped_item["attachments"]:
                        item["attachements"].append(
                            {
                                "name": attachment.name,
                                "path": (
                                    Path(
                                        attachment,
                                    )
                                    .relative_to(self.cache["BASE"])
                                    .as_posix()
                                ),
                            },
                        )
                    del scraped_item["attachments"]
                for d in [
                    "name",
                    "id",
                    "quantity",
                    "item_page",
                    "extra_data",
                ]:
                    del scraped_item[d]
                assert (
                    scraped_item == {}
                ), f"scraped_item is empty: {scraped_item}"
                order["items"].append(item)

            for d in [
                "currency",
                "order_number",
                "extra_data",
                "folder",
                "items",
            ]:
                del scraped_data[d]
            assert scraped_data == {}, f"scraped_data is empty: {scraped_data}"
            # self.pprint(order)
            structure["orders"].append(order)
        self.output_schema_json(structure)

    # Class init
    def __init__(self, options: dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        # self.COUNTRY = self.check_country(options.country)
        super().setup_cache(self.simple_name)
        self.setup_templates()
