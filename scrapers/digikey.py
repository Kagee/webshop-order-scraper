import json
from typing import Final

from .base import BaseScraper


class DigikeyScraper(BaseScraper):
    tla: Final[str] = "DIG"
    name: Final[str] = "Digikey"
    simple_name: Final[str] = "digikey"

    # Methods that use Selenium to scrape webpages in a browser

    # Random utility functions
    def setup_templates(self):
        # pylint: disable=invalid-name
        # URL Templates
        # self.ORDER_LIST_URL: str = {
        #    "no": "https://www.kjell.com/no/mine-sider/mine-kjop",
        # }[self.COUNTRY]
        # self.LOGIN_PAGE_RE: str = r"https://www.kjell.com.*login=required.*"

        # https://www.digikey.no/OrderHistory/ReviewOrder/9910000345121987

        # https://www.digikey.no/no/products/detail/m5stack-technology-co-ltd/K039/13148795
        # https://www.digikey.no/no/products/detail/-/-/13148795
        # pylint: disable=invalid-name
        # self.ORDER_LIST_JSON_FILENAME = (
        #    self.cache["ORDER_LISTS"] / f"kjell-{self.COUNTRY}-orders.json"
        # )
        self.ORDER_LIST_JSON = self.cache["ORDER_LISTS"] / "orders.json"

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        pass

    # Command functions, used in scrape.py
    def command_scrape(self):
        """
        Scrapes your Kjell orders.
        """
        # https://www.digikey.no/OrderHistory/List -> data-autoid="btnDownloadCsv" -> click?
        # if not self.ORDER_LIST_JSON.is_file():
        #    self.log.error("Could not find %s", self.ORDER_LIST_JSON)
        #    self.log.error(
        #        "Visit https://www.digikey.no/OrderHistory/List to download orders.json",
        #    )

        # https://www.digikey.no/OrderHistory/api/orders/invoiceDetails?searchQuery=&shared=False&startDate=2021-01-01 00:00:00&endDate=2024-07-26 23:59:59&pageSize=20&pageStartIndex=1&shared=False
        # 0 - 19 ->  pageStartIndex=20 -> 20 -> 24
        with (self.cache["ORDER_LISTS"] / "invoices.json").open() as f:
            invoices_json = json.load(f)

        orders = {}
        for invoice in invoices_json:
            order_number = invoice["orderNumber"]

            order = {
                "order_number": order_number,
                "items": [],
                "extra_data": {},
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
                "thumbnail": i["imageUrl"],
                "extra_data": {},
            }
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
