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
                "Using SCRAPER_IMAP_FLAG (%s), ignoring SCRAPER_IMAP_FOLDER", settings.SCRAPER_IMAP_FLAGS
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
            folder_mg = imap_client.search(["FROM", "ebay@ebay.com"])
            print(f"Found {len(folder_mg)} messages from eBay")
            messages.append((folder, folder_mg))

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
                    if "transid" in rover:
                        # just get transid + itemid
                        t = re.match(r".*transid(?:%3D|=)([0-9-]+)[^0-9]", rover, re.IGNORECASE)
                        ti = re.match(r".*itemid(?:%3D|=)([0-9-]+)[^0-9].*", rover, re.IGNORECASE)
                        url = "Failed to find bot transid and itemid"
                        foo = ""
                        if t and ti:
                            transid = t.group(1)
                            itemid = ti.group(1)
                            if len(transid) < 13:
                                foo = "Probably to old, but try: "
                            url = f"https://order.ebay.com/ord/show?transid={transid}&itemid={itemid}"
                        res.add("WEB SCRAPE: " + foo + url)
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
                # Images, PDFs, icals, etc. Ignore
                return None

        for m in messages:
            imap_client.select_folder(m[0])

            for uid, message_data in imap_client.fetch(set(m[1]), "RFC822").items():
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
                    )
                    for look in look_at:
                        print(uid, look)

        self.log.debug(imap_client.logout().decode("utf-8"))
