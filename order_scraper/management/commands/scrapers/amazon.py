from django.core.management.base import BaseCommand, CommandError

class AmazonDeScraper():
    def __init__(self, command: BaseCommand, try_file: bool = False):
        self.command = command
        raise CommandError('Scraping of Amazon (DE) not yet implemented')
