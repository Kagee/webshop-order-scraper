#!/usr/bin/env python3
from locale import currency
from tomlkit import item
from bootstrap import python_checks

python_checks()

# pylint: disable=wrong-import-position,wrong-import-order
from scrapers import settings

import argparse
from pathlib import Path
from scrapers.base import BaseScraper
from decimal import Decimal
from datetime import datetime

import logging.config

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
    earliest_date = datetime.now().strftime('%Y-%m-%d')
    total_total = {}
    for order in shop_json["orders"]:
        if order['date'] < earliest_date:
            earliest_date = order['date']
        max_num_items = max(max_num_items, len(order["items"]))
        num_items = num_items + len(order["items"])
        if order["total"]["currency"] not in total_total:
            total_total[order["total"]["currency"]] = Decimal(0)
        total_total[order["total"]["currency"]] = total_total[
            order["total"]["currency"]
        ] + Decimal(order["total"]["value"])

    print("Shop: %s" % shop_json["metadata"]["name"])
    print("Number of orders: %s" % num_order)
    print("Number of items (possible duplicates): %s" % num_items)
    print("Largest order (# items): %s" % max_num_items)
    print("First order: %s" % earliest_date)
    if len(total_total) > 1:
        total_string = []
        for currency in total_total:
            total_string.append("%.2f %s" %(total_total[currency], currency))
        print(
                "Total total: "
                , " + ".join(total_string)
            )
    else:
        for currency in total_total:
            print(
                "Total total: %.2f %s"
                % (total_total[currency], currency)
            )


if __name__ == "__main__":
    main()
