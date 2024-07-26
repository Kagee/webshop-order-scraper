#!/usr/bin/env python3
import argparse
import datetime
import logging.config
import os

from bootstrap import python_checks

python_checks()
# ruff: noqa: E402, F403
from scrapers import *
from scrapers import settings

if settings.GH_TOKEN:
    os.environ["GH_TOKEN"] = settings.GH_TOKEN

logging.config.dictConfig(settings.LOGGING)
log = logging.getLogger("scraper")


def parse_args():  # noqa: PLR0915
    log.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(
        description="Allows you to scrape and save webshop order info",
    )

    parser.add_argument(
        "--loglevel",
        type=str.upper,
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
    )

    parser.add_argument(
        "--no-close-browser",
        action="store_true",
        help="Do not close browser window.",
    )

    subparsers = parser.add_subparsers(
        title="sources",
        description="valid sources",
        help="what source to parse",
        dest="source",
        required=True,
    )

    def to_std_json(parser):
        parser.add_argument(
            "--to-std-json",
            action="store_true",
            help=(
                "Generate schema-valid json for import into Homelag Organizer."
            ),
        )

    def use_cached_orderlist(parser):
        parser.add_argument(
            "--use-cached-orderlist",
            action="store_true",
            help=(
                "Use cached version of orderlist. Will make re-runs more"
                " effective, but will not detect new orders."
            ),
        )

    def skip_order_pdf(parser):
        parser.add_argument(
            "--skip-order-pdf",
            action="store_true",
            help="Do not create or save order-related PDFs like invoices.",
        )

    def skip_item_pdf(parser):
        parser.add_argument(
            "--skip-item-pdf",
            action="store_true",
            help=(
                "Do not create or save item-related PDFs like item listing"
                " PDFs."
            ),
        )

    def skip_item_thumb(parser):
        parser.add_argument(
            "--skip-item-thumb",
            action="store_true",
            help="Do not save item thumbnail",
        )

    def include_negative_orders(parser):
        parser.add_argument(
            "--include-negative-orders",
            action="store_true",
            help="Include orders with negative item count in export.",
        )

    def force_web_scrape(parser):
        parser.add_argument(
            "--force-web-scrape",
            action="store_true",
            help=(
                "Force scraping of order(s) even if cached. "
                "Will probably only update JSON."
            ),
        )

    def force_scrape_item_pdf(parser):
        parser.add_argument(
            "--force-scrape-item-pdf",
            action="store_true",
            help=(
                "Force scraping of order(s) even if cached. "
                "Will probably only update JSON."
            ),
        )

    def force_scrape_order_json(parser):
        parser.add_argument(
            "--force-scrape-order-json",
            action="store_true",
            help=(
                "Force scraping of order(s) even if cached. "
                "Will probably only update JSON."
            ),
        )

    parser_adafruit = subparsers.add_parser("adafruit")

    to_std_json(parser_adafruit)

    parser_aliexpress = subparsers.add_parser("aliexpress")

    use_cached_orderlist(parser_aliexpress)
    to_std_json(parser_aliexpress)

    parser_amazon = subparsers.add_parser("amazon")

    use_cached_orderlist(parser_amazon)
    force_web_scrape(parser_amazon)
    force_scrape_item_pdf(parser_amazon)
    force_scrape_order_json(parser_amazon)
    to_std_json(parser_amazon)

    parser_amazon.add_argument(
        "-y",
        "--year",
        type=str,
        metavar="YEAR[,YEAR...]",
        help=(
            "What year(s) to get orders for. "
            f"Default is current year ({datetime.date.today().year})."  # noqa: DTZ011
        ),
    )
    parser_amazon.add_argument(
        "--start-year",
        type=int,
        help="Get all years, starting at START_YEAR.",
    )

    parser_amazon.add_argument(
        "--tld",
        type=str.lower,
        required=True,
        help="What tld to scrape.",
    )

    parser_amazon.add_argument(
        "--not-archived",
        action="store_true",
        help="Don't scrape archived orders.",
    )

    parser_kjell = subparsers.add_parser("kjell")

    use_cached_orderlist(parser_kjell)
    to_std_json(parser_kjell)

    parser_kjell.add_argument(
        "--country",
        type=str.lower,
        default="no",
        help="What country webshop to scrape. Default `no`",
    )

    parser_distrelec = subparsers.add_parser("distrelec")

    use_cached_orderlist(parser_distrelec)

    parser_distrelec.add_argument(
        "--domain",
        type=str.lower,
        default="www.elfadistrelec.no",
        help="What domain to scrape. Default `www.elfadistrelec.no`",
    )

    parser_ebay = subparsers.add_parser("ebay")
    use_cached_orderlist(parser_ebay)
    to_std_json(parser_ebay)
    skip_item_pdf(parser_ebay)
    skip_item_thumb(parser_ebay)
    force_web_scrape(parser_ebay)

    _ = subparsers.add_parser("imap")

    parser_pimoroni = subparsers.add_parser("digikey")

    parser_pimoroni = subparsers.add_parser("pimoroni")
    use_cached_orderlist(parser_pimoroni)

    parser_komplett = subparsers.add_parser("komplett")
    use_cached_orderlist(parser_komplett)
    to_std_json(parser_komplett)

    parser_polyalkemi = subparsers.add_parser("polyalkemi")
    use_cached_orderlist(parser_polyalkemi)
    to_std_json(parser_polyalkemi)

    skip_order_pdf(parser_polyalkemi)
    skip_item_pdf(parser_polyalkemi)
    skip_item_thumb(parser_polyalkemi)
    include_negative_orders(parser_polyalkemi)

    parser_tindie = subparsers.add_parser("tindie")
    use_cached_orderlist(parser_tindie)
    to_std_json(parser_tindie)
    skip_item_pdf(parser_tindie)
    skip_item_thumb(parser_tindie)

    args = parser.parse_args()

    log.debug("Command line arguments: %s", args)
    return args


def main():
    args = parse_args()
    log.setLevel(level=args.loglevel)

    scraper_class = next(
        y for x, y in globals().items() if x.lower() == args.source + "scraper"
    )
    log.debug("Loaded %s based on %s", scraper_class, args.source)

    if (
        hasattr(args, "to_std_json")
        and args.to_std_json
        and hasattr(scraper_class, "command_to_std_json")
    ):
        scraper_class(args).command_to_std_json()
    elif hasattr(args, "to_std_json") and args.to_std_json:
        log.error("%s does not support to_std_json", args.source)
    else:
        scraper_class(args).command_scrape()


if __name__ == "__main__":
    main()
