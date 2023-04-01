from django.core.management.base import BaseCommand, CommandError

from .base import BaseScraper

class AmazonDeScraper(BaseScraper):
    def __init__(self, command: BaseCommand):
        super().__init__(command)
        raise CommandError('Scraping of Amazon (DE) not yet implemented')
