import email.header
import logging
import re
from email.policy import default as default_policy
from getpass import getpass

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management.base import CommandError
from imapclient import IMAPClient
from imapclient.exceptions import *


class IMAPScraper(object):
    def __init__(self) -> None:
        self.log = logging.getLogger(__name__)

    def command_scrape(self):
        imap_username = (
            input(f"Enter username for {settings.SCRAPER_IMAP_SERVER}: ")
            if not settings.SCRAPER_IMAP_USERNAME
            else settings.SCRAPER_IMAP_USERNAME
        )
        imap_password = (
            getpass(
                f"Enter password for {imap_username} at"
                f" {settings.SCRAPER_IMAP_SERVER}: "
            )
            if not settings.SCRAPER_IMAP_PASSWORD
            else settings.SCRAPER_IMAP_PASSWORD
        )

        self.log.debug(
            "IMAPClient for %s:%s",
            settings.SCRAPER_IMAP_SERVER,
            settings.SCRAPER_IMAP_PORT,
        )
        imap_client = IMAPClient(
            host=settings.SCRAPER_IMAP_SERVER, port=settings.SCRAPER_IMAP_PORT
        )
        try:
            imap_client.login(imap_username, imap_password)
        except LoginError as login_error:
            raise CommandError("Invalid credentials", login_error)
        mailboxes = []
        if settings.SCRAPER_IMAP_FLAGS:
            self.log.debug(
                "Using SCRAPER_IMAP_FLAG, ignoring SCRAPER_IMAP_FOLDER"
            )

            for folder in imap_client.list_folders():
                if any(
                    [
                        flag
                        for flag in folder[0]
                        if any(
                            f
                            for f in settings.SCRAPER_IMAP_FLAGS
                            if flag.decode("utf-8") == f
                        )
                    ]
                ):
                    self.log.debug(
                        "Folder '%s' has one of flags '%s'",
                        folder[2],
                        ", ".join(settings.SCRAPER_IMAP_FLAGS),
                    )
                    mailboxes.append(folder[2])

        elif settings.SCRAPER_IMAP_FOLDERS:
            self.log.debug("Using SCRAPER_IMAP_FOLDER")
            mailboxes = settings.SCRAPER_IMAP_FOLDERS
        else:
            self.log.debug("Looking in AAAAAALLLL mailboxes")
            for folder in imap_client.list_folders():
                mailboxes.append(folder[2])

        messages = []
        for folder in mailboxes:
            self.log.debug("Selecting folder %s", folder)
            imap_client.select_folder(folder)
            messages = messages + imap_client.search(["FROM", "ebay@ebay.com"])

        def find_in_plaintext(uid, content):
            transid = re.findall(
                r"(?:cartid|transId|transid)(?:%3D|=)([0-9]+)[^0-9]",
                content,
                re.MULTILINE | re.DOTALL,
            )
            if transid:
                return set(transid)
            return None

        def find_in_html(uid, content):
            soup = BeautifulSoup(content, features="lxml")
            rovers = re.findall(
                r".*rover\.ebay\.com.*",
                soup.prettify(),
                re.IGNORECASE,
            )
            res = set()
            for rover in rovers:
                if "payments.ebay.com" in rover and (
                    "transid" in rover or "chartid" in rover
                ):
                    res.add("MAIL SCRAPE")
                else:
                    if "transid" in rover:
                        # just get transid + itemid
                        res.add("WEB SCRAPE")
            if res:
                return res
            return None

        def process_not_multipart(part):
            content = part.get_content()
            if part.get_content_type() == "text/plain":
                r = find_in_plaintext(uid, content)
                if r:
                    return r
            elif part.get_content_type() == "text/html":
                r = find_in_html(uid, content)
                if r:
                    return r
            else:
                body = part.get_content()[0:1000].split("\n")[0:10]
                for line in body:
                    print(line)
            return None

        for uid, message_data in reversed(
            imap_client.fetch(messages, "RFC822").items()
        ):
            email_message: email.message.EmailMessage = (
                email.message_from_bytes(
                    message_data[b"RFC822"], policy=default_policy
                )
            )
            look_at = None
            if email_message.is_multipart():
                for part in email_message.walk():
                    if not part.is_multipart():
                        look_at = process_not_multipart(part)
            else:
                look_at = process_not_multipart(email_message)

            if look_at:
                print(
                    "We should take a look at",
                    uid,
                    email.header.decode_header(email_message.get("Date"))[0][0],
                    look_at,
                )

        self.log.debug(imap_client.logout().decode("utf-8"))