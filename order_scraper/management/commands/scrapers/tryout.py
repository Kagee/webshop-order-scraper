# pylint: disable=unused-import
import os
import re
import time
from pathlib import Path
from typing import Dict, List
from lxml.etree import tostring
from lxml.html.soupparser import fromstring
from django.conf import settings
from django.core.management.base import BaseCommand
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
import random
import string
from .base import BaseScraper, PagePart


# Scraper for trying out code for other scrapers
class TryOutScraper(BaseScraper):
    def __init__(self, command: BaseCommand, options: Dict):
        super().__init__(command, options, __name__)
        self.LOGIN_PAGE_RE = r"^https://www\.amazon\.de/ap/signin"
        self.setup_cache("tryout")

    def part_to_filename(self, part: PagePart, **kwargs):
        return None

    def command_scrape(self):

        brws = self.browser_get_instance(emulate_mobile_browser=True)

        time.sleep(3000)
        self.browser_safe_quit()

    def browser_cleanup_item_page(self):
        brws = self.browser
        self.log.debug("Hide fluff, ads, etc")
        elemets_to_hide: List[WebElement] = []
        for element in [
            (By.XPATH, "//div[contains(@class, 'ComparisonWidget')]"),
            (By.CSS_SELECTOR, "div.a-carousel-row"),
            (By.CSS_SELECTOR, "div.a-carousel-header-row"),
            (By.CSS_SELECTOR, "div.a-carousel-container"),
            (By.CSS_SELECTOR, "div.widgetContentContainer"),
            (By.CSS_SELECTOR, "div.adchoices-container"),
            (By.CSS_SELECTOR, "div.ad"),
            (By.CSS_SELECTOR, "div.copilot-secure-display"),
            (By.CSS_SELECTOR, "div.outOfStock"),
            # share-button, gives weird artefacts on PDF
            (By.CSS_SELECTOR, "div.ssf-background"),
            (By.ID, "imageBlockEDPOverlay"),
            (By.ID, "aplusBrandStory_feature_div"),
            (By.ID, "value-pick-ac"),
            (By.ID, "valuePick_feature_div"),
            (By.ID, "orderInformationGroup"),
            (By.ID, "navFooter"),
            (By.ID, "navbar"),
            (By.ID, "similarities_feature_div"),
            (By.ID, "dp-ads-center-promo_feature_div"),
            (By.ID, "ask-btf_feature_div"),
            (By.ID, "customer-reviews_feature_div"),
            (By.ID, "rhf-container"),
            (By.ID, "rhf-frame"),
            (By.ID, "productAlert_feature_div"),
            (By.ID, "sellYoursHere_feature_div"),
            (By.ID, "rightCol"),
            (By.ID, "sp-cc"),  # Cookies, if not logged in
            (By.TAG_NAME, "hr"),
            (By.TAG_NAME, "iframe"),
        ]:
            elemets_to_hide += brws.find_elements(element[0], element[1])
        brws.execute_script(
            """
                // remove spam/ad elements
                for (let i = 0; i < arguments[0].length; i++) {
                    arguments[0][i].remove()
                }
                // Give product text more room
                arguments[1].style.marginRight=0
                arguments[2].scrollIntoView()
                """,
            elemets_to_hide,
            brws.find_element(By.CSS_SELECTOR, "div.centerColAlign"),
            brws.find_element(By.ID, "rightCol"),
        )
        time.sleep(2)

    # No login
    def browser_login2(self, url):
        pass

    def browser_login(self, _):
        """
        Uses Selenium to log in Amazon.
        Returns when the browser is at url, after login.

        Raises and alert in the browser if user action
        is required.
        """
        if settings.SCRAPER_AMZ_MANUAL_LOGIN:
            pass
        else:
            # We (optionally) ask for this here and not earlier, since we
            # may not need to go live
            self.username = settings.SCRAPER_AMZ_USERNAME
            self.password = settings.SCRAPER_AMZ_PASSWORD

            self.log.info(
                self.command.style.NOTICE("We need to log in to amazon.%s"),
                "de",
            )
            brws = self.browser_get_instance()

            wait = WebDriverWait(brws, 10)
            try:
                self.rand_sleep()
                username = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_email"))
                )
                username.send_keys(self.username)
                self.rand_sleep()
                wait.until(
                    EC.element_to_be_clickable(((By.ID, "continue")))
                ).click()
                self.rand_sleep()
                password = wait.until(
                    EC.presence_of_element_located((By.ID, "ap_password"))
                )
                password.send_keys(self.password)
                self.rand_sleep()
                remember = wait.until(
                    EC.presence_of_element_located((By.NAME, "rememberMe"))
                )
                remember.click()
                self.rand_sleep()
                sign_in = wait.until(
                    EC.presence_of_element_located(
                        (By.ID, "auth-signin-button")
                    )
                )
                sign_in.click()
                self.rand_sleep()

            except TimeoutException:
                self.browser_safe_quit()
                # pylint: disable=raise-missing-from
                print(
                    "Login to Amazon was not successful "
                    "because we could not find a expected element.."
                )
        if re.match(self.LOGIN_PAGE_RE, self.browser.current_url):
            print("Login to Amazon was not successful.")
        self.log.info("Login to Amazon was probably successful.")
