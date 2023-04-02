from django.core.management.base import (BaseCommand, CommandError,
                                         no_translations)

from .scrapers.aliexpress import AliExpressScraper
from .scrapers.amazon import AmazonScraper

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
                    "amazon.es",
                    "amazon.se"
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
            AmazonScraper(self, 'de', options).command_scrape()
        elif options['webshop'] == "amazon.co.uk":
            AmazonScraper(self, 'co.uk', options).command_scrape()
        elif options['webshop'] == "amazon.com":
            AmazonScraper(self, 'com', options).command_scrape()
        elif options['webshop'] == "amazon.co.jp":
            AmazonScraper(self, 'co.jp', options).command_scrape()
        elif options['webshop'] == "amazon.es":
            AmazonScraper(self, 'es', options, archived="No hay pedidos").command_scrape()
        elif options['webshop'] == "amazon.se":
            AmazonScraper(self, 'se', options, archived="Det finns inga arkiverade").command_scrape()

        #
        # https://en.wikipedia.org/wiki/Amazon_(company)#Amazon.com
        #
        # Will *probably* work with minor monifications, but not tested:
        # amazon.com.br - Brazil
        # amazon.ca - Canada
        # amazon.com.mx - Mexico
        # amazon.in - India
        # amazon.sg - Singapore
        # amazon.com.tr - Turkey
        # amazon.com.be - Belgium
        # amazon.fr - France
        # amazon.it - Italy
        # amazon.nl - Netherlands
        # amazon.pl - Poland
        # amazon.au - Australia
        #
        # More than minor modifications may be required
        # amazon.eg - Egypt - Formerly souq.com, modifications may be required
        # amazon.cn - China -  Formerly joyo.com, modifications may be required
        # amazon.sa - Saudi Arabia - Formerly souq.com, modifications may be required
        # amazon.ae - United Arab Emirates - Formerly souq.com, modifications may be required
        else:
            raise CommandError("Unknown webshop: {options['webshop']}")
