from pathlib import Path
from typing import Dict

from django.core.management.base import BaseCommand
from selenium import webdriver


class BaseScraper(object):
    browser: webdriver.Firefox
    browser_status: str = "no-created"
    orders: list
    username: str
    password: str
    cache: Dict[str, Path]
    pdf_temp_file: Path
    log = None
    command: BaseCommand
    log = None

    def __init__(self, command: BaseCommand):
        self.command = command
