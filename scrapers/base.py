import argparse
import base64
import contextlib
import csv
import datetime
import decimal
import json
import logging
import math
import os
import pprint
import random
import re
import shutil
import time
import urllib.request
import zipfile
from datetime import date
from decimal import Decimal
from enum import Enum
from getpass import getpass
from json.encoder import JSONEncoder
from logging import Logger
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import filetype
import requests
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
from webdriver_manager.core.driver_cache import DriverCacheManager
from webdriver_manager.firefox import GeckoDriverManager as FirefoxDriverManager

from . import settings

# pylint: disable=unused-import
from .utils import AMBER, BLUE, RED


class PagePart(Enum):
    ORDER_LIST_JSON = 1
    ORDER_LIST_HTML = 2
    ORDER_DETAILS = 3
    ORDER_ITEM = 4


class BaseScraper:
    browser: webdriver.Firefox
    browser_status: str = "no-created"
    orders: list
    username: str
    password: str
    cache: dict[str, Path]
    log: Logger
    options: argparse.Namespace
    LOGIN_PAGE_RE: str = r".+login.example.com.*"
    name: str = "Base"
    simple_name: str = "base"
    tla: str = "BSE"

    def __init__(
        self,
        options: argparse.Namespace,
        logname: str,
    ):
        self.options = options
        self.log = logging.getLogger(logname)
        self.log.setLevel(options.loglevel)
        # pylint: disable=invalid-name
        self.makedir(Path(settings.CACHE_BASE))
        self.log.debug("Init complete: %s/%s", __name__, logname)

    def valid_json(self, structure):
        with settings.JSON_SCHEMA.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
            try:
                validate(instance=structure, schema=schema)
            except ValidationError as vde:
                self.log.error(  # noqa: TRY400
                    RED("JSON failed validation: %s at %s"),
                    vde.message,
                    vde.json_path,
                )
                return False
        return True

    def get_structure(self, name, branch_name, order_url, item_url):
        return {
            "metadata": {
                "name": name,
                "branch_name": branch_name if branch_name else name,
                "order_url": order_url,
                "item_url": item_url,
                "generator": "gitlab.com/Kagee/web-order-scraper",
            },
            "orders": [],
        }

    # @classmethod
    def get_value_currency(self, name, value, force_currency=None):
        """Will assume $ is USD and € is EUR, we can do better"""
        if isinstance(value, str):
            guess_price = Price.fromstring(value)
        else:
            guess_price = Price(
                amount=Decimal(value),
                currency=None,
                amount_text=str(value),
            )
        if not guess_price.amount:
            self.log.warning(
                AMBER("name: %s, value: %s, force_currency: %s"),
                name,
                value,
                force_currency,
            )
            guess_price.amount = 0
        amount = guess_price.amount
        if isinstance(amount, Decimal):
            amount = amount.quantize(
                decimal.Decimal(".00"),
                decimal.ROUND_HALF_UP,
            ) + Decimal("0.00")
        amount_str = str(amount)
        if amount_str == "0":
            amount_str = "0.00"
        value_curr_dict = {"value": amount_str}

        if force_currency:
            curr_dict = {"currency": force_currency}
        elif guess_price.currency in ["$", "USD"]:
            curr_dict = {"currency": "USD"}
        elif guess_price.currency in ["€", "EUR"]:
            curr_dict = {"currency": "EUR"}
        elif guess_price.currency in ["￥", "JPY"]:
            curr_dict = {"currency": "JPY"}
        elif guess_price.currency in ["£", "GBP"]:
            curr_dict = {"currency": "GBP"}
        elif guess_price.currency in ["NOK"]:
            curr_dict = {"currency": "NOK"}
        elif value == "Free shipping":
            curr_dict = {}
        else:
            self.log.warning(
                AMBER("name: %s, value: %s, force_currency: %s"),
                name,
                value,
                force_currency,
            )
            self.log.warning(
                AMBER("Unexpected value/currency: %s/%s/%s"),
                name,
                value,
                guess_price.currency,
            )
            msg = (
                "Unexpected value/currency:"
                f" {name}/{value}/{guess_price.currency}"
            )
            raise NotImplementedError(
                msg,
            )

        value_curr_dict.update(curr_dict)
        return value_curr_dict

    def output_schema_json(self, structure):
        # Validate json structure
        self.log.debug("Validating JSON structure")
        if self.valid_json(structure):
            self.makedir(settings.OUTPUT_FOLDER)
            json_file_path = Path(
                settings.OUTPUT_FOLDER,
                self.simple_name + ".json",
            ).resolve()
            zip_file_path = json_file_path.with_suffix(".zip")
            self.log.debug(
                "Removing old output file %s and %s from %s",
                json_file_path.name,
                zip_file_path.name,
                json_file_path.parent,
            )

            self.remove(json_file_path)
            self.remove(zip_file_path)

            self.log.debug("Generating zip file list... ")
            files_from_to = []
            for order in structure["orders"]:
                if "attachements" in order:
                    for attach in order["attachements"]:
                        orig_file = self.cache["BASE"] / attach["path"]
                        files_from_to.append((orig_file, attach["path"]))
                for item in order["items"]:
                    if "thumbnail" in item:
                        orig_file = self.cache["BASE"] / item["thumbnail"]
                        files_from_to.append((orig_file, item["thumbnail"]))
                    if "attachements" in item:
                        for attach in item["attachements"]:
                            orig_file = self.cache["BASE"] / attach["path"]
                            files_from_to.append((orig_file, attach["path"]))

            count_files = len(files_from_to)
            if count_files > 0:
                self.log.debug(
                    "Copying %s files to %s",
                    count_files,
                    zip_file_path,
                )
                per_count = max(10, math.ceil(count_files / 20))
                with zipfile.ZipFile(zip_file_path, "a") as zip_file:
                    for count, data in enumerate(files_from_to):
                        if count % per_count == 0:
                            self.log.info(
                                "Added %s of %s files to %s",
                                count,
                                count_files,
                                zip_file_path.name,
                            )
                        zip_file.write(data[0], data[1])
                    logo = Path(f"logos/{self.simple_name}.png")
                    if self.can_read(logo):
                        zip_file.write(logo, "logo.png")
                        self.log.debug("Added %s as logo.png", logo.name)
                    else:
                        self.log.warning(
                            AMBER("Found no %s in logos/"),
                            logo.name,
                        )
            else:
                self.log.warning(AMBER("No files to add to zip, not creating"))
            self.log.debug("Writing JSON to %s", json_file_path)
            with json_file_path.open("w", encoding="utf-8") as json_file:
                json_file.write(json.dumps(structure, indent=4))

            self.log.info("Export successful")

    def setup_cache(self, base_folder: Path):
        self.cache: dict[str, Path] = {
            "BASE": Path(settings.CACHE_BASE, base_folder),
        }
        self.cache.update(
            {
                "ORDER_LISTS": self.cache["BASE"] / Path("order_lists"),
                "ORDERS": self.cache["BASE"] / Path("orders"),
                "TEMP": self.cache["BASE"] / Path("temporary"),
            },
        )
        for name, path in self.cache.items():
            self.log.debug("Cache folder %s: %s", name, path)
            self.makedir(path)

        self.cache.update(
            {"PDF_TEMP_FILENAME": self.cache["TEMP"] / "temporary.pdf"},
        )
        self.cache.update(
            {"IMG_TEMP_FILENAME": self.cache["TEMP"] / "temporary.jpg"},
        )

    def find_element(
        self,
        by_obj: str,
        value: str | None,
        element=None,
    ) -> WebElement:
        try:
            if not element:
                element = self.browser_get_instance()
            return element.find_element(by_obj, value)
        except NoSuchElementException:
            return None

    def find_elements(
        self,
        by_obj: str,
        value: str | None,
        element=None,
    ) -> list[WebElement]:
        try:
            if not element:
                element = self.browser_get_instance()
            return element.find_elements(by_obj, value)
        except NoSuchElementException:
            return []

    def browser_setup_login_values(self, change_ua=None):
        if getattr(settings, f"{self.tla}_MANUAL_LOGIN"):
            self.log.debug(
                BLUE(
                    f"Please log in manually to {self.name} and press enter"
                    " when ready.",
                ),
            )
            input()
            return self.browser_get_instance(change_ua), None, None
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
        return (
            self.browser_get_instance(change_ua),
            username_data,
            password_data,
        )

    def browser_get_instance(self, change_ua=None) -> webdriver.Firefox:
        """
        Initializing and configures a browser (Firefox)
        using Selenium.

        Returns a exsisting object if avaliable.

            Returns:
                browser (WebDriver): the configured and initialized browser
        """
        if self.browser_status != "created":
            self.log.debug("Loading Firefox webdriver binary")
            os.environ["WDM_LOG"] = str(logging.NOTSET)

            service = FirefoxService(
                executable_path=FirefoxDriverManager(
                    cache_manager=DriverCacheManager(),  #  , version="v0.33.0"
                ).install(),
            )
            self.log.debug("Initializing browser")
            options = Options()

            # Configure printing
            options.add_argument("-profile")
            options.add_argument(str(settings.FF_PROFILE_PATH))
            options.set_preference("profile", str(settings.FF_PROFILE_PATH))
            options.set_preference("print.always_print_silent", value=True)
            options.set_preference("print_printer", settings.PDF_PRINTER)
            self.log.debug("Printer set to %s", settings.PDF_PRINTER)
            printer_name = settings.PDF_PRINTER.replace(" ", "_")
            options.set_preference(
                f"print.printer_{ printer_name }.print_to_file",
                value=True,
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

            options.set_preference("browser.download.folderList", value=2)
            options.set_preference(
                "browser.download.manager.showWhenStarting",
                value=False,
            )
            options.set_preference(
                "browser.download.alwaysOpenInSystemViewerContextMenuItem",
                value=False,
            )
            options.set_preference(
                "browser.download.alwaysOpenPanel",
                value=False,
            )
            options.set_preference(
                "browser.download.dir",
                str(self.cache["TEMP"]),
            )
            options.set_preference(
                "browser.helperApps.neverAsk.saveToDisk",
                "application/pdf",
            )
            options.set_preference(
                "pdfjs.disabled",
                value=True,
            )
            options.set_preference(
                f"print.printer_{ printer_name }.print_to_filename",
                str(self.cache["PDF_TEMP_FILENAME"]),
            )
            options.set_preference(
                f"print.printer_{ printer_name }.show_print_progress",
                value=True,
            )
            if change_ua:
                options.set_preference(
                    "general.useragent.override",
                    change_ua,
                )
            options.set_preference("detach", value=True)
            self.log.info("Starting browser")
            self.browser = webdriver.Firefox(options=options, service=service)

            self.browser_status = "created"
            self._browser_post_init()
            self.log.debug("Returning browser")
        return self.browser

    @property
    def b(self):
        return self.browser_get_instance()

    def _browser_post_init(self):
        # Stuff we should do before returning the first browser session
        return

    def browser_safe_quit(self):
        """
        Safely closed the browser instance. (without exceptions)
        """
        try:
            if self.browser_status == "created":
                if self.options.no_close_browser:
                    self.log.info(
                        "Not closing browser because of --no-close-browser",
                    )
                    return
                self.log.info("Safely closing browser")
                self.browser.quit()
                self.browser_status = "quit"
        except WebDriverException:
            pass

    def browser_visit(self, url: str):
        brws = self.browser_get_instance()
        brws.get(url)
        self.browser_detect_handle_interrupt(url)
        return brws

    def browser_visit_page(
        self,
        url: str,
        *,
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
                    " Probably something wrong happened.",
                )
            # We were redirected to the login page
            self.browser_login(url)
            if goto_url_after_login:
                self.browser_visit_page(
                    url,
                    goto_url_after_login,
                    do_login=False,
                )
        else:
            self.log.debug("Login not required")

    def browser_login(self, _expected_url):
        if True:
            msg = "Child does not implement browser_login()"
            raise NotImplementedError(
                msg,
            )

    def browser_detect_handle_interrupt(self, _expected_url) -> None:
        if True:
            msg = (
                "Child does not implement browser_detect_handle_interrupt(self,"
                " expected_url)..."
            )
            raise NotImplementedError(
                msg,
            )

    def part_to_filename(self, _part: PagePart, **_kwargs):
        if True:
            msg = "Child does not implement _part_to_filename(...)"
            raise NotImplementedError(
                msg,
            )

    def has_json(self, part: PagePart, **kwargs) -> bool:
        return self.can_read(self.part_to_filename(part, **kwargs))

    def read_json(self, part: PagePart, **kwargs) -> Any:
        if not self.has_json(part, **kwargs):
            return {}
        return self.read(self.part_to_filename(part, **kwargs), from_json=True)

    @classmethod
    def pprint(cls, value: Any) -> None:
        pprint.PrettyPrinter(indent=2).pprint(value)

    def clear_folder(self, folder: Path | None = None):
        if folder is None:
            folder = self.cache["TEMP"]
        for filename in folder.glob("*"):
            filename.unlink()

    def download_url_to_file(self, url: str, output: Path):
        output.parent.mkdir(exist_ok=True)
        with urllib.request.urlopen(  # noqa: S310
            url,
        ) as response, output.open(
            "wb",
        ) as output_handle:
            shutil.copyfileobj(response, output_handle)

    def external_download_image(
        self,
        glob: str,
        url: str,
        folder: Path | None = None,
    ):
        """
        Downloads image from url if no file matching glob in folder was found

        Returns path to downloaded file or None if a exsisting file was found
        """

        if folder is None:
            folder = self.cache["TEMP"]
        self.log.debug(
            "External image download. glob: %s, folder: %s, url: %s",
            glob,
            folder,
            url,
        )
        if not list(Path(folder).glob(glob)):
            self.clear_folder(folder)
            headers = {
                "User-Agent": (
                    "python/webshop-order-scraper (hildenae@gmail.com)"
                ),
            }
            response = requests.get(url=url, headers=headers, timeout=10)
            url_parsed = urlparse(url)
            image_name = Path(url_parsed.path).name
            image_path = self.cache["TEMP"] / image_name
            self.write(
                image_path,
                response.content,
                binary=True,
            )
            kind = filetype.guess(image_path)
            if kind.mime.startswith("image/") and kind.extension in [
                "jpg",
                "png",
            ]:
                return image_path
            self.log.error(
                "Thumbnail was not JPEG/PNG: %s, %s",
                kind.mime,
                kind.extension,
            )
            raise NotImplementedError
        # A file was found, nothing downloaded
        return None

    def wait_for_files(
        self,
        glob: str,
        folder: Path | None = None,
    ) -> list[Path]:
        if folder is None:
            folder = self.cache["TEMP"]
        files = list(folder.glob(glob))
        wait_count = 0
        while not files:
            files = list(folder.glob(glob))
            time.sleep(3)
            wait_count += 1
            if wait_count > 60:  # noqa: PLR2004
                self.log.error(
                    RED(
                        "We have been waiting for a file for 3 minutes,"
                        " something is wrong...",
                    ),
                )
                msg = f"{folder}/{glob}"
                raise NotImplementedError(msg)
        return files

    def rand_sleep(self, min_seconds: int = 0, max_seconds: int = 5) -> None:
        """
        Wait rand(min_seconds(0), max_seconds(5)), so we don't spam Amazon.
        """
        time.sleep(random.randint(min_seconds, max_seconds))  # noqa: S311

    def move_file(
        self,
        old_path: Path,
        new_path: Path,
        *,
        overwrite: bool = True,
    ):
        if not overwrite and self.can_read(new_path):
            self.log.info(
                "Not overriding existing file: %s",
                Path(new_path).name,
            )
            return
        while True:
            try:
                if overwrite:
                    self.remove(new_path)
                old_path.rename(new_path)
            except PermissionError as permerr:
                self.log.debug(permerr)
                time.sleep(3)
                continue
            break

    def makedir(self, path: Path | str) -> None:
        with contextlib.suppress(FileExistsError):
            path.mkdir(parents=True)

    def remove(self, path: Path | str) -> bool:
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        else:
            return True

    def can_read(self, path: Path | str):
        return os.access(path, os.R_OK)

    def write(
        self,
        path: Path | str,
        content: Any,
        *,
        to_json=False,
        binary=False,
        html=False,
        from_base64=False,
    ):
        kwargs = {"encoding": "utf-8"}
        write_mode = "w"
        if not isinstance(path, Path):
            path = Path(path)
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
        with path.open(
            write_mode,
            **kwargs,
        ) as file:
            file.write(content)
        if html:
            return html_element
        return content

    @classmethod
    def read(
        cls,
        path: Path | str,
        *,
        from_json=False,
        from_html=False,
        from_csv=False,
        **kwargs,
    ) -> Any:
        with path.open(encoding="utf-8-sig") as file:
            if from_csv:
                return list(csv.DictReader(file, **kwargs))
            contents: str = file.read()
            if from_json:
                try:
                    contents = json.loads(contents)
                except json.decoder.JSONDecodeError as jde:
                    cls.log.exception("Encountered error when reading %s", path)
                    msg = f"Encountered error when reading {path}"
                    raise OSError(
                        msg,
                        jde,
                    ) from jde
            elif from_html:
                contents = fromstring(contents)
            return contents

    def wait_for_stable_file(self, filename: Path | str):
        while not self.can_read(filename):
            self.log.debug("File does not exist yet: %s", filename.name)
            time.sleep(1)
        size_stable = False
        counter = 10
        while not size_stable:
            sz1 = filename.stat().st_size
            time.sleep(2)
            sz2 = filename.stat().st_size
            time.sleep(2)
            sz3 = filename.stat().st_size
            size_stable = (sz1 == sz2 == sz3) and sz1 + sz2 + sz3 > 0
            self.log.debug(
                "Watching for stable file size larger than 0 bytes: %s %s"
                " %s %s",
                sz1,
                sz2,
                sz3,
                Path(filename).name,
            )
            counter -= 1
            if counter == 0:
                msg = (
                    f"Waited 40 seconds for {filename} to be stable, never"
                    " stabilized."
                )
                raise OSError(
                    msg,
                )
        self.log.debug("File %s appears stable.", filename)

    def browser_cleanup_page(
        # We are not modifying the values
        # pylint: disable=dangerous-default-value
        self,
        xpaths: list | None = None,
        ids: list | None = None,
        css_selectors: list | None = None,
        element_tuples: list | None = None,
    ) -> None:
        if element_tuples is None:
            element_tuples = []
        if css_selectors is None:
            css_selectors = []
        if ids is None:
            ids = []
        if xpaths is None:
            xpaths = []
        if len(xpaths + ids + css_selectors + element_tuples) == 0:
            self.log.debug(
                "browser_cleanup_page called, but no cleanup defined",
            )
            return

        brws = self.browser
        self.log.debug("Hiding elements (fluff, ads, etc.) using Javscript")
        elemets_to_hide: list[WebElement] = []

        for element_xpath in xpaths:
            elemets_to_hide += brws.find_elements(By.XPATH, element_xpath)

        for element_id in ids:
            elemets_to_hide += brws.find_elements(By.ID, element_id)

        for css_selector in css_selectors:
            elemets_to_hide += brws.find_elements(By.CSS_SELECTOR, css_selector)

        for element_tuple in element_tuples:
            elemets_to_hide += brws.find_elements(
                By.CSS_SELECTOR,
                element_tuple,
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
    ) -> dict[date, dict[str, tuple[int, str]]]:
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
                    line["OBS_VALUE"],
                    decimal_separator=",",
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
        today = datetime.datetime.now().astimezone().date()
        if last_day < today:
            for created_date_index in daterange(last_day, today):
                data_dict[str(created_date_index)] = data_dict[last_day]
            data_dict[str(today)] = data_dict[last_day]
        return {str(key): value for (key, value) in data_dict.items()}


class WSJSONEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, Path):
            return str(o)
        if isinstance(o, datetime.datetime):
            return str(o)
        return super().default(o)
