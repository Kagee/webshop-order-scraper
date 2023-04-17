import logging
import os
import email.header
import sys
from getpass import getpass

from click import Command
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from imapclient import IMAPClient
from imapclient.exceptions import *
from email.policy import default as default_policy


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
        self.client = IMAPClient(
            host=settings.SCRAPER_IMAP_SERVER, port=settings.SCRAPER_IMAP_PORT
        )
        try:
            self.client.login(
                settings.SCRAPER_IMAP_USERNAME, settings.SCRAPER_IMAP_PASSWORD
            )
        except LoginError as le:
            raise CommandError("Invalid credentials", le)
        mailboxes = []
        if settings.SCRAPER_IMAP_FLAGS:
            self.log.debug(
                "Using SCRAPER_IMAP_FLAG, ignoring SCRAPER_IMAP_FOLDER"
            )

            for folder in self.client.list_folders():
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
            self.log.error(
                "HLO_SCRAPER_IMAP_FLAG or HLOSCRAPER_IMAP_FOLDER must be set."
            )
            raise CommandError()
        messages = []
        for folder in mailboxes:
            self.log.debug("Selecting folder %s", folder)
            self.client.select_folder(folder)
            messages = messages + self.client.search(["FROM", "ebay@ebay.com"])

        interesting_messages = []
        ignore_subj = [
            "A new device is using your account",
            "Privacy Notice",
            "sent a message",
            "New sign in activity",
        ]

        for uid, message_data in self.client.fetch(messages, "RFC822").items():
            email_message: email.message.EmailMessage = (
                email.message_from_bytes(
                    message_data[b"RFC822"], policy=default_policy
                )
            )
            subject = email.header.decode_header(email_message.get("Subject"))

            subject = (
                subject[0][0].decode(subject[0][1])
                if subject[0][1]
                else subject[0][0]
            )
            if any([x for x in ignore_subj if x in subject]):
                continue
            print(uid, email_message.get("From"), subject)
            for part in email_message.walk():
                if part.get_content_type() != "multipart/mixed":
                    print(
                        uid,
                        part.get("Content-Type"),
                        part.get_charsets(),
                        part.get("Content-Transfer-Encoding"),
                    )
                    print(
                        uid,
                    )
                    payload = part.get_payload(decode=True)
                    if payload:
                        # print(
                        #    uid,
                        #    payload.decode(part.get_charsets()[0]),
                        # )
                        pass
                    else:
                        print(
                            uid,
                            part,
                        )
                    # )
                # if part.get_content_type() != :
                #    for part in email_message.walk():
                #        print(type(part))
                # print(part.as_string())

        self.log.debug(self.client.logout().decode("utf-8"))

    # with  as client:
    #    print(
    #    print("")
    #
    #    print("")
    #    print(len(client.search(['FROM', '"*@ebay.com"'])))
    #    print("")
    #
    #    print(M.noop())
    #    print(M.utf8_enabled)
    #    lst = M.list()
    #    if lst[0]:
    #        for item in lst[1]:
    #            print(item.decode("utf-8"))
    #    print(M.select("INBOX"))
    #    print(M.search(None, 'FROM', '"@ebay.com"'))
    #    print(M.logout())
    #
