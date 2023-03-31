import logging
from pathlib import Path
from typing import Dict

from django.core.management.base import BaseCommand
from selenium import webdriver


class BaseScraper():
    browser: webdriver.Firefox
    orders: list
    username: str
    password: str
    try_file: bool
    cache: Dict[str, Path]
    pdf_temp_file: Path
    log = logging.getLogger(__name__)
    command: BaseCommand

    def __init__(self, command: BaseCommand, try_file: bool = False):
        self.try_file = try_file
        self.command = command
