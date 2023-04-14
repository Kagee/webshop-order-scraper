import datetime
import logging
import os

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, no_translations

from ...models.shop import Shop
from .scrapers.adafruit import AdafruitScraper
from .scrapers.aliexpress import AliExpressScraper
from .scrapers.amazon import AmazonScraper
from .scrapers.distrelec import DistrelecScraper
from .scrapers.tryout import TryOutScraper


class Command(BaseCommand):
    help = "Scrapes a webshop for orders using Selenium"
    requires_migrations_checks = True

    def add_arguments(self, parser):
        # Creation order is backwards to trick help-print-order
        dec = parser.add_argument_group("distrelec-spesific scraper options")
        dec.add_argument(
            "-d",
            "--domain",
            type=str.lower,
            default="www.elfadistrelec.no",
            help="What domain to scrape. Default `www.elfadistrelec.no`",
        )

        amz = parser.add_argument_group("amazon-spesific scraper options")
        amz.add_argument(
            "-y",
            "--year",
            type=str,
            metavar="YEAR[,YEAR...]",
            help=(
                "What year(s) to get orders for. "
                f"Default is current year ({datetime.date.today().year})."
            ),
        )
        amz.add_argument(
            "--start-year",
            type=int,
            help="Get all years, starting at START_YEAR.",
        )

        amz.add_argument(
            "--tld",
            type=str.lower,
            default="de",
            help="What tld to scrape. Default `de`",
        )

        amz.add_argument(
            "--not-archived",
            action="store_true",
            help="Don't scrape archived orders.",
        )

        scraper = parser.add_argument_group()
        # Apparently we do not support subparsers
        scraper.add_argument(
            "webshop",
            type=str.lower,
            nargs="?",
            choices=["aliexpress", "amazon", "distrelec", "adafruit", "tryout"],
            help="The online webshop to scrape orders from. (REQUIRED)",
        )

        scraper.add_argument(
            "--use-cached-orderlist",
            action="store_true",
            help=(
                "Use cached version of orderlist. Will make re-runs more"
                " effective, but will not detect new orders."
            ),
        )

        scraper.add_argument(
            "--no-close-browser",
            action="store_true",
            help="Leave browser window open after scraping/unexpected stops.",
        )
        scraper.add_argument(
            "--random",
            action="store_true",
            help=(
                "Process orders/items in random order. Not supported by all"
                " scrapers."
            ),
        )
        scraper.add_argument(
            "--init-shops",
            action="store_true",
            help=(
                "Initialize database with some data. "
                "Can be used to update data."
            ),
        )
        scraper.add_argument(
            "--load-to-db",
            action="store_true",
            help="Load all currently parsed data to DB.",
        )
        scraper.add_argument(
            "--db-shop-id",
            type=int,
            default=-1,
            choices=list(Shop.objects.values_list("id", flat=True)),
            help="Load data into this database shop. "
            + ", ".join(
                f"{x[0]} - {x[1]}"
                for x in Shop.objects.values_list("id", "branch_name")
            ),
        )
        # Internal hack to get command-spesific options on top
        parser._action_groups.reverse()  # pylint: disable=protected-access

    def setup_logger(self, options):
        log = logging.getLogger(__name__)
        if options["verbosity"] == 0:
            # 0 = minimal output
            log.setLevel(logging.ERROR)
        elif options["verbosity"] == 1:
            # 1 = normal output
            log.setLevel(logging.WARNING)
        elif options["verbosity"] == 2:
            # 2 = verbose output
            log.setLevel(logging.INFO)
        elif options["verbosity"] == 3:
            # 3 = very verbose output
            log.setLevel(logging.DEBUG)
        self.log = log

    @no_translations
    def handle(self, *_, **options):
        if options["webshop"] == "aliexpress":
            if options["load_to_db"]:
                AliExpressScraper(self, options).command_load_to_db()
            else:
                AliExpressScraper(self, options).command_scrape()
        elif options["webshop"] == "amazon":
            AmazonScraper(self, options).command_scrape()
        elif options["webshop"] == "distrelec":
            DistrelecScraper(self, options).command_scrape()
        elif options["webshop"] == "adafruit":
            if options["load_to_db"]:
                AdafruitScraper(self, options).command_load_to_db()
            else:
                AdafruitScraper(self, options).command_scrape()
        elif options["webshop"] == "tryout":
            TryOutScraper(self, options).command_scrape()
        else:
            if options["init_shops"]:
                self.setup_logger(options)
                self.log.debug("Initializing database with shops")
                for shop in [
                    (
                        "Adafruit",
                        None,
                        "https://www.adafruit.com/index.php?main_page=account_history_info&order_id={order_id}",
                        "https://www.adafruit.com/product/{item_id}",
                    ),
                    (
                        "Amazon",
                        "Amazon.de",
                        "https://www.amazon.de/gp/your-account/order-details/?orderID={order_id}",
                        "https://www.amazon.de/-/en/gp/product/{item_id}",
                    ),
                    (
                        "Aliexpress",
                        None,
                        "https://www.aliexpress.com/p/order/detail.html?orderId={order_id}",
                        "https://www.aliexpress.com/item/{item_id}.html",
                    ),
                ]:
                    branch_name = shop[1] if shop[1] else shop[0]
                    logo_path = (
                        settings.BASE_DIR / f"logos/{branch_name.lower()}.png"
                    )
                    logo_img = None
                    if os.access(logo_path, os.R_OK):
                        logo_img = File(open(logo_path, "rb"), logo_path.name)

                    (shop_object, created) = Shop.objects.update_or_create(
                        name=shop[0],
                        branch_name=branch_name,
                        defaults={
                            "order_url_template": shop[2] if shop[2] else "",
                            "item_url_template": shop[3] if shop[3] else "",
                        },
                    )
                    if logo_img:
                        if shop_object.icon:
                            shop_object.icon.delete()
                        shop_object.icon = logo_img
                        shop_object.save()
                        logo_img.close()
                    if created:
                        self.log.debug("Created new shop: %s", shop_object)
                    else:
                        self.log.debug(
                            "Found and possibly updated: %s", shop_object
                        )
