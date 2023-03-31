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

        parser.add_argument(
                '-c',
                '--cache',
                action='store_true',
                help="Use file cache of webshop orders if avaliable (mostly for development)"
                )

        parser.add_argument(
                '-i',
                '--indent',
                action='store_true',
                help="Loop and indent cache files (mostly for development)"
                )

    @no_translations
    def handle(self, *args, **options):
        if options['webshop'] == "aliexpress":
            if options['indent']:
                AliScraper(self, options['cache']).command_indent()
            else:
                AliScraper(self, options['cache']).command_scrape()
        elif options['webshop'] == "amazon.de":
            AmazonDeScraper(self, options['cache'])
        else:
            raise CommandError("Unknown webshop: {options['webshop']}")
