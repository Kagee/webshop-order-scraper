import base64
import csv
import datetime
import json
import logging
import math
import os
import pprint
import random
import re
import time
import zipfile
from datetime import date
from decimal import Decimal
from enum import Enum
from getpass import getpass
from json.encoder import JSONEncoder
from logging import Logger
from pathlib import Path
from typing import Any, Dict, List, Union

from jsonschema import ValidationError, validate
from lxml.etree import tostring
from lxml.html.soupparser import fromstring
from price_parser import Price
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webelement import WebElement
from webdriver_manager.firefox import GeckoDriverManager as FirefoxDriverManager

from . import settings

# pylint: disable=unused-import
from .utils import AMBER, BLUE, GREEN, RED


class PagePart(Enum):
    ORDER_LIST_JSON = 1
    ORDER_LIST_HTML = 2
    ORDER_DETAILS = 3
    ORDER_ITEM = 4


class BaseScraper(object):
    browser: webdriver.Firefox
    browser_status: str = "no-created"
    orders: list
    username: str
    password: str
    cache: Dict[str, Path]
    log: Logger
    options: Dict
    LOGIN_PAGE_RE: str = r".+login.example.com.*"
    name: str = "Base"
    simple_name: str = "base"
    tla: str = "BSE"

    def __init__(
        self,
        options: Dict,
        logname: str,
    ):
        self.options = options
        self.log = logging.getLogger(logname)
        self.log.setLevel(options.loglevel)
        # pylint: disable=invalid-name
        self.makedir(Path(settings.CACHE_BASE))
        self.log.debug("Init complete: %s/%s", __name__, logname)

    def valid_json(self, structure):
        with open("schema.json", encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
            try:
                validate(instance=structure, schema=schema)
            except ValidationError as vde:
                self.log.error(
                    RED("JSON failed validation: %s at %s"),
                    vde.message,
                    vde.json_path,
                )
                return False
        return True

    def get_structure(self, name, branch_name, order_url, item_url):
        return {
            "metadata": {
                "name": "Aliexpress",
                "branch_name": name if not branch_name else branch_name,
                "order_url": (
                    "https://www.aliexpress.com/p/"
                    "order/detail.html?orderId={order_id}"
                ),
                "item_url": "https://www.aliexpress.com/item/{item_id}.html",
            },
            "orders": [],
        }

    def output_schema_json(self, structure):
        # Validate json structure
        self.log.debug("Validating JSON structure")
        if self.valid_json(structure):
            self.makedir(settings.EXPORT_FOLDER)
            json_file_path = Path(
                settings.EXPORT_FOLDER, self.simple_name + ".json"
            ).resolve()
            zip_file_path = json_file_path.with_suffix(".zip")
            self.log.debug(
                "Removing old output filee %s and %s from %s",
                json_file_path.name,
                zip_file_path.name,
                json_file_path.parent,
            )

            self.remove(json_file_path)
            self.remove(zip_file_path)
            self.log.debug("Writing JSON to %s", zip_file_path)
            with open(json_file_path, "w", encoding="utf-8") as json_file:
                json_file.write(json.dumps(structure, indent=4))

            self.log.debug("Copying files to %s", zip_file_path)
            with zipfile.ZipFile(zip_file_path, "a") as zip_file:
                for order in structure["orders"]:
                    for item in order["items"]:
                        orig_file = self.cache["BASE"] / item["thumbnail"]
                        zip_file.write(orig_file, item["thumbnail"])
                        for attach in item["attachements"]:
                            orig_file = self.cache["BASE"] / attach["path"]
                            zip_file.write(orig_file, attach["path"])

            self.log.info(
                "Export successful to %s and %s in %s",
                json_file_path.name,
                zip_file_path.name,
                json_file_path.parent,
            )

    def setup_cache(self, base_folder: Path):
        self.cache: Dict[str, Path] = {
            "BASE": Path(settings.CACHE_BASE, base_folder)
        }
        self.cache.update(
            {
                "ORDER_LISTS": self.cache["BASE"] / Path("order_lists"),
                "ORDERS": self.cache["BASE"] / Path("orders"),
                "TEMP": self.cache["BASE"] / Path("temporary"),
            }
        )
        for name, path in self.cache.items():
            self.log.debug("Cache folder %s: %s", name, path)
            self.makedir(path)

        self.cache.update(
            {"PDF_TEMP_FILENAME": self.cache["TEMP"] / "temporary-pdf.pdf"}
        )

    def find_element(
        self, by_obj: str, value: Union[str, None], element=None
    ) -> Union[WebElement, None]:
        try:
            if not element:
                element = self.browser
            return element.find_element(by_obj, value)
        except NoSuchElementException:
            return None

    def find_elements(
        self, by_obj: str, value: Union[str, None], element=None
    ) -> Union[WebElement, None]:
        try:
            if not element:
                element = self.browser
            return element.find_elements(by_obj, value)
        except NoSuchElementException:
            return []

    def browser_setup_login_values(self):
        if getattr(settings, f"{self.tla}_MANUAL_LOGIN"):
            self.log.debug(
                BLUE(
                    f"Please log in manually to {self.name} and press enter"
                    " when ready."
                )
            )
            input()
            return self.browser_get_instance(), None, None
        else:
            # We (optionally) ask for this here and not earlier, since we
            # may not need to go live
            username_data = (
                input(f"Enter {self.name} username:")
                if not getattr(settings, f"{self.tla}_USERNAME")
                else getattr(settings, f"{self.tla}_USERNAME")
            )
            password_data = (
                getpass(f"Enter {self.name} password:")
                if not getattr(settings, f"{self.tla}_PASSWORD")
                else getattr(settings, f"{self.tla}_PASSWORD")
            )

            self.log.info(AMBER(f"Trying to log in to {self.name}"))
            return self.browser_get_instance(), username_data, password_data

    def browser_get_instance(self, change_ua=None):
        """
        Initializing and configures a browser (Firefox)
        using Selenium.

        Returns a exsisting object if avaliable.

            Returns:
                browser (WebDriver): the configured and initialized browser
        """
        if self.browser_status != "created":
            self.log.debug(
                "Using Selenium webdriver_manager to download webdriver binary"
            )
            service = FirefoxService(
                executable_path=FirefoxDriverManager().install()
            )
            self.log.debug("Initializing browser")
            options = Options()

            # Configure printing
            options.set_preference("print.always_print_silent", True)
            options.set_preference("print_printer", settings.PDF_PRINTER)
            self.log.debug("Printer set to %s", settings.PDF_PRINTER)
            printer_name = settings.PDF_PRINTER.replace(" ", "_")
            options.set_preference(
                f"print.printer_{ printer_name }.print_to_file", True
            )
            # Hide all printing metadata so it is easier to use
            # pdf2text
            # URL at top of page &U
            options.set_preference("print.print_headercenter", "")
            options.set_preference("print.print_headerleft", "")
            options.set_preference("print.print_headerright", "")
            # Page X of Y and date & time on bottom of page &PT - &D
            options.set_preference("print.print_footercenter", "")
            options.set_preference("print.print_footerleft", "")
            options.set_preference("print.print_footerright", "")

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
                "browser.download.dir", str(self.cache["TEMP"])
            )
            options.set_preference(
                "browser.helperApps.neverAsk.saveToDisk", "application/pdf"
            )
            options.set_preference("pdfjs.disabled", True)
            options.set_preference(
                f"print.printer_{ printer_name }.print_to_filename",
                str(self.cache["PDF_TEMP_FILENAME"]),
            )
            options.set_preference(
                f"print.printer_{ printer_name }.show_print_progress", True
            )
            if change_ua:
                options.set_preference(
                    "general.useragent.override",
                    change_ua,
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
                if self.options.no_close_browser:
                    self.log.info(
                        "Not cloding browser because of --no-close-browser"
                    )
                    return
                self.log.info("Safely closing browser")
                self.browser.quit()
                self.browser_status = "quit"
        except WebDriverException:
            pass

    def browser_visit_page(
        self,
        url: str,
        goto_url_after_login: bool = True,
        do_login: bool = True,
        default_login_detect: bool = True,
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
        if default_login_detect:
            self.browser_login_required(url, goto_url_after_login, do_login)
        else:
            self.browser_detect_handle_interrupt(url)
        return self.browser

    def browser_visit_page_v2(self, url: str):
        return self.browser_visit_page(
            url,
            goto_url_after_login=False,
            do_login=False,
            default_login_detect=False,
        )

    def browser_login_required(self, url, goto_url_after_login, do_login):
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

    def browser_login(self, expected_url):
        raise NotImplementedError("Child does not implement browser_login()")

    def browser_detect_handle_interrupt(self, expected_url) -> None:
        pass

    def part_to_filename(self, part: PagePart, **kwargs):
        raise NotImplementedError(
            "Child does not implement _part_to_filename(...)"
        )

    def has_json(self, part: PagePart, **kwargs) -> bool:
        return self.can_read(self.part_to_filename(part, **kwargs))

    def read_json(self, part: PagePart, **kwargs) -> Any:
        if not self.has_json(part, **kwargs):
            return {}
        return self.read(self.part_to_filename(part, **kwargs), from_json=True)

    def pprint(self, value: Any) -> None:
        pprint.PrettyPrinter(indent=2).pprint(value)

    def rand_sleep(self, min_seconds: int = 0, max_seconds: int = 5) -> None:
        """
        Wait rand(min_seconds(0), max_seconds(5)), so we don't spam Amazon.
        """
        time.sleep(random.randint(min_seconds, max_seconds))

    def move_file(self, old_path: Path, new_path: Path, overwrite: bool = True):
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
            content = base64.b64decode(content, validate=True)
        if to_json:
            content = json.dumps(content, indent=4, cls=WSJSONEncoder)
        if html:
            html_element = fromstring(content)
            content = tostring(html_element).decode("utf-8")
        if binary:
            write_mode += "b"
            kwargs = {}
        with open(  # pylint: disable=unspecified-encoding
            path, write_mode, **kwargs
        ) as file:
            file.write(content)
        if html:
            return html_element
        return content

    def read(
        self,
        path: Union[Path, str],
        from_json=False,
        from_html=False,
        from_csv=False,
        **kwargs,
    ) -> Any:
        with open(path, "r", encoding="utf-8-sig") as file:
            if from_csv:
                contents = list(csv.DictReader(file, **kwargs))
            else:
                contents = file.read()
            if from_json:
                try:
                    contents = json.loads(contents)
                except json.decoder.JSONDecodeError as jde:
                    self.log.error("Encountered error when reading %s", path)
                    raise IOError(
                        f"Encountered error when reading {path}", jde
                    ) from jde
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
                Path(filename).name,
            )
            counter -= 1
            if counter == 0:
                raise IOError(
                    f"Waited 40 seconds for {filename} to be stable, never"
                    " stabilized."
                )
        self.log.debug("File %s appears stable.", filename)

    def browser_cleanup_page(
        self,
        xpaths: List = None,
        ids: List = None,
        css_selectors: List = None,
        element_tuples: List = None,
    ) -> None:
        if len(xpaths + ids + css_selectors + element_tuples) == 0:
            self.log.debug(
                "browser_cleanup_page called, but no cleanup defined"
            )
            return

        brws = self.browser
        self.log.debug("Hiding elements (fluff, ads, etc.) using Javscript")
        elemets_to_hide: List[WebElement] = []

        for element_xpath in xpaths:
            elemets_to_hide += brws.find_elements(By.XPATH, element_xpath)

        for element_id in ids:
            elemets_to_hide += brws.find_elements(By.ID, element_id)

        for css_selector in css_selectors:
            elemets_to_hide += brws.find_elements(By.CSS_SELECTOR, css_selector)

        for element_tuple in element_tuples:
            elemets_to_hide += brws.find_elements(
                By.CSS_SELECTOR, element_tuple
            )

        brws.execute_script(
            """
                // remove spam/ad elements
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].remove()
                }
                """,
            elemets_to_hide,
        )

    def load_currency_to_nok_dict(
        self,
    ) -> Dict[date, Dict[str, tuple[int, str]]]:
        input_csv = settings.CACHE_BASE / "EXR.csv"
        self.log.debug("Loading currency conversion data from %s", input_csv)
        index: dict = self.read(
            input_csv,
            from_csv=True,
            delimiter=";",
        )
        data_dict = {}

        for line in index:
            date_name = date.fromisoformat(line["TIME_PERIOD"])
            if date_name not in data_dict:
                data_dict[date_name] = {}
            data_dict[date_name][line["BASE_CUR"]] = (
                Decimal(math.pow(10, int(line["UNIT_MULT"]))),
                Price.fromstring(
                    line["OBS_VALUE"], decimal_separator=","
                ).amount,
            )

        def daterange(start_date, end_date):
            for num_days in range(int((end_date - start_date).days - 1)):
                yield start_date + datetime.timedelta(num_days + 1)

        sorted_data_dict = sorted(data_dict.keys())

        prev_date = None
        self.log.debug("Filling missing dates with previous valid date")
        for idx, date_index in enumerate(sorted_data_dict):
            if idx > 0:
                for created_date_index in daterange(
                    prev_date,
                    date_index,
                ):
                    data_dict[str(created_date_index)] = data_dict[prev_date]
                    prev_date = str(created_date_index)
            prev_date = date_index

        last_day = sorted_data_dict[len(sorted_data_dict) - 1]
        if last_day < date.today():
            for created_date_index in daterange(last_day, date.today()):
                data_dict[str(created_date_index)] = data_dict[last_day]
            data_dict[str(date.today())] = data_dict[last_day]
        return {str(key): value for (key, value) in data_dict.items()}


class WSJSONEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, Path):
            return str(o)
        if isinstance(o, datetime.datetime):
            return str(o)
        return super().default(o)
