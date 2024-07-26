# ruff: noqa: C901,ERA001,PLR0912,PLR0915
import json
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
            order_number = invoice["orderNumber"]
            order_folder: Path = self.cache["ORDERS"] / str(order_number)
            order_folder.mkdir(exist_ok=True)

            order = {
                "order_number": order_number,
                "items": [],
                "extra_data": {},
                "folder": order_folder,
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
            order_number = details["orderNumber"]

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
                "id": i["productId"],
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
                "thumbnail_url": i["imageUrl"].replace("//", "https://"),
                "extra_data": {},
                "folder": item_folder,
            }
            self.download_url_to_file()
            new_thmb = Path(item["folder"] / f"thumbnail")
            thmb = self.external_download_image(item["thumbnail_url"])
                "thumbnail-*",
                ,
                ,
            )

            kind = filetype.guess(image_path)
            if kind.mime.startswith("image/") and kind.extension in [
                "jpg",
                "png",
            ]:
                return image_path

            print(thmb)

            thmb.rename(new_thmb)
            import sys

            print(thmb)
            print(new_thmb)
            print(new_thmb.is_file())
            sys.exit(1)
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

        self.pprint(orders, 260)
        self.log.debug(self.cache)
        """
        invoiceDetails.json:
        [
            { // repeatet multiple with same orderNumber
                invoiceDetails [{

                "description" name
                 "manufacturerProductNumber": "SMD291",
                "description": "FLUX NO-CLEAN 10CC SYR SMD",
                "manufacturerName": "Chip Quik Inc.",
                }]
            }
        ]

        orders.json:
        [
            {
            "orderNumber": 9910000345121988,
            "currencyIso": "NOK",
            "status": "Shipped",
            "dateEntered": "2024-02-15T21:01:59.068Z",
            "invoices": [ // can be more than one
            {
                  "orderValue": 43594, // /100 in currencyIso // subtotal (uten levering, uten vat)
                     "webId": 345121987,
                "complete": true,
                "salesOrderId": 85436710,
            "boxes": [ // can be more than one
            {
            "carrier": "DHL",
            "dateTransaction": "2024-02-15T22:48:59.858Z",
            "dateShipped": "2024-02-15T23:03:48.032Z",
            "carrierPackageId": "5973990024",
        """
        # self.browser_safe_quit()

    def command_to_std_json(self):
        """
        Convert all data we have to a JSON that validates with schema,
         and a .zip with all attachements
        """
        structure = self.get_structure(
            self.name,
            None,
            "https://www.kjell.com/no/mine-sider/mine-kjop#{order_id}",
            "https://www.kjell.com/-p{item_id}",
        )
        # self.output_schema_json(structure)

    # Class init
    def __init__(self, options: dict):
        super().__init__(options, __name__)
        # pylint: disable=invalid-name
        # self.COUNTRY = self.check_country(options.country)
        super().setup_cache(self.simple_name)
        self.setup_templates()
