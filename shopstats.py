#!/usr/bin/env python3
# ruff: noqa: T201, E402
from bootstrap import python_checks

python_checks()

# pylint: disable=wrong-import-position,wrong-import-order
import argparse
import logging.config
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from scrapers import settings
from scrapers.base import BaseScraper

logging.config.dictConfig(settings.LOGGING)
log = logging.getLogger("shopstats")
log.debug("Base logging configured")


def parse_args():
    log.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(
        description="Show stats per shop based on JSON export",
    )

    parser.add_argument(
        "--loglevel",
        type=str.upper,
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
    )

    subparsers = parser.add_subparsers(
        title="sources",
        description="valid sources",
        help="what shop to get stas for",
        dest="source",
        required=True,
    )

    for x in Path(settings.OUTPUT_FOLDER).glob("*.json"):
        if x.stem != "schema":
            subparsers.add_parser(x.stem)
    args = parser.parse_args()

    log.debug("Command line arguments: %s", args)
    return args


def main():
    args = parse_args()
    log.setLevel(level=args.loglevel)
    shop_json = BaseScraper.read(
        Path(settings.OUTPUT_FOLDER) / Path(args.source + ".json"),
        from_json=True,
    )
    num_order = len(shop_json["orders"])
    num_items = 0
    max_num_items = 0
    earliest_date = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    total_total = {}
    for order in shop_json["orders"]:
        if order["date"] < earliest_date:
            earliest_date = order["date"]
        max_num_items = max(max_num_items, len(order["items"]))
        num_items = num_items + len(order["items"])
        log.debug(
            "%s: %s %s",
            order["id"],
            order["total"]["value"],
            order["total"]["currency"],
        )
        if order["total"]["currency"] not in total_total:
            total_total[order["total"]["currency"]] = Decimal(0)
        total_total[order["total"]["currency"]] = total_total[
            order["total"]["currency"]
        ] + Decimal(order["total"]["value"].replace(",", "."))

    branch = (
        ""
        if shop_json["metadata"]["name"] == shop_json["metadata"]["branch_name"]
        else f" ({shop_json['metadata']['branch_name']})"
    )
    print(f"Shop: {shop_json['metadata']['name']}{branch}")
    print(f"Number of orders: {num_order}")
    print(f"Number of items (possible duplicates): {num_items}")
    print(f"Largest order (# items): {max_num_items}")
    print(f"First order: {earliest_date}")
    if len(total_total) > 1:
        total_string = []
        for currency in total_total:
            total_string.append(f"{total_total[currency]:.2f} {currency}")  # noqa: PERF401
        print("Total total: ", " + ".join(total_string))
    else:
        for currency in total_total:
            print(f"Total total: {total_total[currency]:.2f} {currency}")


if __name__ == "__main__":
    main()
