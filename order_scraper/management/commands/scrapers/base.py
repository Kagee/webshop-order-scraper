import base64
import json
import logging
import os
import pprint
import random
import re
import time
from enum import Enum
from logging import Logger
from pathlib import Path
from typing import Any, Dict, Union

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from lxml.etree import tostring
from lxml.html.soupparser import fromstring
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager as FirefoxDriverManager


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
    LOGIN_PAGE_RE: str = r".+login.example.com.*"
    PDF_TEMP_FILENAME: str
    PDF_TEMP_FOLDER: str

    class Part(Enum):
        ORDER_LIST = 1
        ORDER_DETAILS = 2
        ORDER_ITEM = 3

    def __init__(
        self,
        command: BaseCommand,
        options: Dict,
        logname: str,
    ):
        self.options = options
        self.log = self.setup_logger(logname)
        self.command = command

        # pylint: disable=invalid-name
        self.makedir(Path(settings.SCRAPER_CACHE_BASE))

    def setup_logger(self, logname: str) -> Logger:
        log = logging.getLogger(logname)
        if self.options["verbosity"] == 0:
            # 0 = minimal output
            log.setLevel(logging.ERROR)
        elif self.options["verbosity"] == 1:
            # 1 = normal output
            log.setLevel(logging.WARNING)
        elif self.options["verbosity"] == 2:
            # 2 = verbose output
            log.setLevel(logging.INFO)
        elif self.options["verbosity"] == 3:
            # 3 = very verbose output
            log.setLevel(logging.DEBUG)
        return log

    def setup_cache(self, base_folder: Path):
        self.cache: Dict[str, Path] = {
            "BASE": Path(settings.SCRAPER_CACHE_BASE, base_folder)
        }
        self.cache.update(
            {
                "ORDER_LISTS": self.cache["BASE"] / Path("order_lists"),
                "ORDERS": self.cache["BASE"] / Path("orders"),
            }
        )
        for name, path in self.cache.items():
            self.log.debug("Cache folder %s: %s", name, path)
            self.makedir(path)

        # pylint: disable=invalid-name
        self.PDF_TEMP_FOLDER: Path = self.cache["BASE"] / Path("temporary-pdf/")
        self.makedir(self.PDF_TEMP_FOLDER)

        self.PDF_TEMP_FILENAME: Path = self.PDF_TEMP_FOLDER / Path(
            "temporary-pdf.pdf"
        )

    def browser_get_instance(self):
        """
        Initializing and configures a browser (Firefox)
        using Selenium.

        Returns a exsisting object if avaliable.

            Returns:
                browser (WebDriver): the configured and initialized browser
        """
        if self.browser_status != "created":
            self.log.info(
                "Using Selenium webdriver_manager to download webdriver binary"
            )
            service = FirefoxService(
                executable_path=FirefoxDriverManager().install()
            )
            self.log.debug("Initializing browser")
            options = Options()

            # Configure printing
            options.set_preference("print.always_print_silent", True)
            options.set_preference(
                "print_printer", settings.SCRAPER_PDF_PRINTER
            )
            self.log.debug("Printer set to %s", settings.SCRAPER_PDF_PRINTER)
            printer_name = settings.SCRAPER_PDF_PRINTER.replace(" ", "_")
            options.set_preference(
                f"print.printer_{ printer_name }.print_to_file", True
            )

            options.set_preference(f"print.print_headercenter", "&U")
            options.set_preference(f"print.print_headerleft", "")
            options.set_preference(f"print.print_headerright", "")
            options.set_preference(f"print.print_footercenter", "&PT - &D")
            options.set_preference(f"print.print_footerleft", "")
            options.set_preference(f"print.print_footerright", "")

            options.set_preference("browser.download.folderList", 2)
            options.set_preference(
                "browser.download.manager.showWhenStarting", False
            )
            options.set_preference(
                "browser.download.alwaysOpenInSystemViewerContextMenuItem",
                False,
            )
            options.set_preference("browser.download.alwaysOpenPanel", False)
            options.set_preference(
                "browser.download.dir", str(self.PDF_TEMP_FOLDER)
            )
            options.set_preference(
                "browser.helperApps.neverAsk.saveToDisk", "application/pdf"
            )
            options.set_preference("pdfjs.disabled", True)
            self.log.debug(
                "PDF temporary file is %s", str(self.PDF_TEMP_FOLDER)
            )
            options.set_preference(
                f"print.printer_{ printer_name }.print_to_filename",
                str(self.PDF_TEMP_FILENAME),
            )
            options.set_preference(
                f"print.printer_{ printer_name }.show_print_progress", True
            )

            self.browser = webdriver.Firefox(options=options, service=service)

            self.browser_status = "created"
            self.log.debug("Returning browser")
        return self.browser

    def browser_safe_quit(self):
        """
        Safely closed the browser instance. (without exceptions)
        """
        try:
            if self.browser_status == "created":
                self.log.info("Safely closing browser")
                self.browser.quit()
                self.browser_status = "quit"
        except WebDriverException:
            pass

    def browser_visit_page(
        self, url: str, goto_url_after_login: bool, do_login=True
    ):
        """
        Instructs the browser to visit url.

        If there is no browser instance, creates one.
        If login is required, does that.

            Returns:
                browser: (WebDriver) the browser instance
        """
        self.browser = self.browser_get_instance()
        self.browser.get(url)

        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            if not do_login:
                self.log.critical(
                    "We were told not to log in, but we are at the login url."
                    " Probably something wrong happened."
                )
            # We were redirected to the login page
            self.browser_login(url)
            if goto_url_after_login:
                self.browser_visit_page(
                    url, goto_url_after_login, do_login=False
                )
        return self.browser

    def browser_login(self, url):
        raise NotImplementedError("Child does not implement browser_login()")

    def _part_to_filename(self, part: Part, **kwargs):
        raise NotImplementedError(
            "Child does not implement _part_to_filename(...)"
        )

    def has_json(self, part: Part, **kwargs) -> bool:
        return self.can_read(self._part_to_filename(part, **kwargs))

    def read_json(self, part: Part, **kwargs) -> Any:
        if not self.has_json(part, **kwargs):
            return {}
        return self.read(self._part_to_filename(part, **kwargs), from_json=True)

    def pprint(self, value: Any) -> None:
        pprint.PrettyPrinter(indent=2).pprint(value)

    def rand_sleep(self, min_seconds: int = 0, max_seconds: int = 5) -> None:
        """
        Wait rand(min_seconds(0), max_seconds(5)), so we don't spam Amazon.
        """
        time.sleep(random.randint(min_seconds, max_seconds))

    def move_file(self, old_path, new_path, overwrite=True):
        if not overwrite and self.can_read(new_path):
            self.log.info(
                "Not overriding existing file: %s",
                Path(new_path).name,
            )
            return
        if overwrite:
            self.remove(new_path)
        os.rename(old_path, new_path)

    def makedir(self, path: Union[Path, str]) -> None:
        try:
            os.makedirs(path)
        except FileExistsError:
            pass

    def remove(self, path: Union[Path, str]) -> bool:
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return False

    def can_read(self, path: Union[Path, str]):
        return os.access(path, os.R_OK)

    def write(
        self,
        path: Union[Path, str],
        content: Any,
        to_json=False,
        binary=False,
        html=False,
        from_base64=False,
    ):
        kwargs = {"encoding": "utf-8"}
        write_mode = "w"
        if from_base64:
            content = base64.b64decode(content)
        if to_json:
            content = json.dumps(content, indent=4, cls=DjangoJSONEncoder)
        if html:
            html_element = fromstring(content)
            content = tostring(html_element).decode("utf-8")
        if binary:
            write_mode += "b"
            kwargs = {}
        else:
            with open(path, write_mode, **kwargs) as file:
                file.write(content)
        if html:
            return html_element
        return content

    def read(
        self, path: Union[Path, str], from_json=False, from_html=False
    ) -> Any:
        with open(path, "r", encoding="utf-8") as file:
            contents = file.read()
            if from_json:
                contents = json.loads(contents)
            elif from_html:
                contents = fromstring(contents)
            return contents

    def wait_for_stable_file(self, filename: Union[Path, str]):
        while not self.can_read(filename):
            self.log.debug("File does not exist yet: %s", filename.name)
            time.sleep(1)
        size_stable = False
        counter = 10
        while not size_stable:
            sz1 = os.stat(filename).st_size
            time.sleep(2)
            sz2 = os.stat(filename).st_size
            time.sleep(2)
            sz3 = os.stat(filename).st_size
            size_stable = (sz1 == sz2 == sz3) and sz1 + sz2 + sz3 > 0
            self.log.debug(
                (
                    "Watching for stable file size larger than 0 bytes: %s %s"
                    " %s %s"
                ),
                sz1,
                sz2,
                sz3,
                filename,
            )
            counter -= 1
            if counter == 0:
                raise CommandError(
                    f"Waited 40 seconds for {filename} to be stable, never"
                    " stabilized."
                )
        self.log.debug("File %s appears stable.", filename)
