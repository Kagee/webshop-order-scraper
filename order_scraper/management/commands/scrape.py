from django.core.management.base import BaseCommand, CommandError, no_translations
from .scrapers.ali import AliScraper
from .scrapers.amazon import AmazonDeScraper

class Command(BaseCommand):
    help = 'Scrapes a webshop for orders using Selenium'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument(
                'webshop',
                type=str.lower,
                choices=["aliexpress", "amazon.de"],
                help="The online webshop to scrape orders from"
                )

    @no_translations
    def handle(self, *args, **options):
        if options['webshop'] == "aliexpress":
            AliScraper(self).command_scrape()
        elif options['webshop'] == "amazon.de":
            AmazonDeScraper(self)
        else:
            raise CommandError("Unknown webshop: {options['webshop']}")
