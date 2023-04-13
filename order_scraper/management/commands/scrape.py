import datetime

from django.core.management.base import BaseCommand, no_translations

from .scrapers.aliexpress import AliExpressScraper
from .scrapers.amazon import AmazonScraper
from .scrapers.distrelec import DistrelecScraper
from .scrapers.adafruit import AdafruitScraper
from .scrapers.tryout import TryOutScraper
from ...models.shop import Shop


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
            choices=["aliexpress", "amazon", "distrelec", "adafruit", "tryout"],
            help="The online webshop to scrape orders from. (REQUIRED)",
        )

        scraper.add_argument(
            "-c",
            "--cache-orderlist",
            action="store_true",
            help=(
                "Use file for order list. Will not detect new orders with this."
            ),
        )

        scraper.add_argument(
            "-b",
            "--do-not-close-browser",
            action="store_true",
            help="Leave browser window open after scraping.",
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

    @no_translations
    def handle(self, *_, **options):
        if options["webshop"] == "aliexpress":
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
