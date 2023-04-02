import logging
import random
import time
from logging import Logger
from pathlib import Path
from typing import Dict

from django.conf import settings
from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import \
    GeckoDriverManager as FirefoxDriverManager


class BaseScraper(object):
    browser: webdriver.Firefox
    browser_status: str = "no-created"
    orders: list
    username: str
    password: str
    cache: Dict[str, Path]
    pdf_temp_file: Path
    log: Logger
    command: BaseCommand
    options: Dict

    def __init__(self, command: BaseCommand, options: Dict):
        self.command = command
        self.options = options

    def setup_logger(self, logname: str) -> Logger:
        log = logging.getLogger(logname)
        if self.options['verbosity'] == 0:
            # 0 = minimal output
            log.setLevel(logging.ERROR)
        elif self.options['verbosity'] == 1:
            # 1 = normal output
            log.setLevel(logging.WARNING)
        elif self.options['verbosity'] == 2:
            # 2 = verbose output
            log.setLevel(logging.INFO)
        elif self.options['verbosity'] == 3:
            # 3 = very verbose output
            log.setLevel(logging.DEBUG)
        return log

    def browser_get_instance(self):
        '''
        Initializing and configures a browser (Firefox)
        using Selenium.

        Returns a exsisting object if avaliable.

            Returns:
                browser (WebDriver): the configured and initialized browser
        '''
        if self.browser_status != "created":
            service = FirefoxService(executable_path=FirefoxDriverManager().install())
            self.log.debug("Initializing browser")
            options = Options()

            # Configure printing
            options.set_preference('print.always_print_silent', True)
            options.set_preference('print_printer', settings.SCRAPER_PDF_PRINTER)
            self.log.debug("Printer set to %s", settings.SCRAPER_PDF_PRINTER)
            printer_name = settings.SCRAPER_PDF_PRINTER.replace(" ","_")
            options.set_preference(f'print.printer_{ printer_name }.print_to_file', True)
            options.set_preference(
                f'print.printer_{ printer_name }.print_to_filename', str(self.pdf_temp_file))
            options.set_preference(
                f'print.printer_{ printer_name }.show_print_progress', True)

            self.browser = webdriver.Firefox(options=options, service=service)

            self.browser_status = "created"
            self.log.debug("Returning browser")
        return self.browser

    def browser_safe_quit(self):
        '''
        Safely closed the browser instance. (without exceptions)
        '''
        try:
            if self.browser_status == "created":
                self.log.info("Safely closing browser")
                self.browser.quit()
                self.browser_status = "quit"
        except WebDriverException:
            pass

    def rand_sleep(self, min_seconds: int = 2, max_seconds: int = 5) -> None:
        """
        Wait rand(min_seconds, max_seconds), so we don't spam Amazon.
        """
        time.sleep(random.randint(min_seconds, max_seconds))
