from django.core.management.base import (BaseCommand, CommandError,
                                         no_translations)

from .scrapers.aliexpress import AliExpressScraper
from .scrapers.amazon_co_jp import AmazonCoJpScraper
from .scrapers.amazon_co_uk import AmazonCoUkScraper
from .scrapers.amazon_com import AmazonComScraper
from .scrapers.amazon_de import AmazonDeScraper


class Command(BaseCommand):
    help = 'Scrapes a webshop for orders using Selenium'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        # Apparently we do not support subparsers
        parser.add_argument(
                'webshop',
                type=str.lower,
                choices=[
                    "aliexpress",
                    "amazon.de",
                    "amazon.co.uk",
                    "amazon.com",
                    "amazon.co.jp",
                    ],
                help="The online webshop to scrape orders from"
                )
        parser.add_argument(
                '-c',
                '--cache-orderlist',
                action='store_true',
                help="Use file for order list. Will not detect new orders with this."
                )
        parser.add_argument(
            "-y",
            "--year",
            default="-1",
            type=str,
            help="What year(s, comma separated) to get orders for. "
            "Only used for Amazon.* scrapers. "
            "Default is -1, all years."
        )
        parser.add_argument(
                '-a',
                '--archived',
                action='store_true',
                help="Also scrape archived orders. Only used for Amazon.* scrapers."
                )
    @no_translations
    def handle(self, *args, **options):
        if options['webshop'] == "aliexpress":
            AliExpressScraper(self, options).command_scrape()
        elif options['webshop'] == "amazon.de":
            AmazonDeScraper(self, options).command_scrape()
        elif options['webshop'] == "amazon.co.uk":
            AmazonCoUkScraper(self, options).command_scrape()
        elif options['webshop'] == "amazon.com":
            AmazonComScraper(self, options).command_scrape()
        elif options['webshop'] == "amazon.co.jp":
            AmazonCoJpScraper(self, options).command_scrape()
        else:
            raise CommandError("Unknown webshop: {options['webshop']}")
