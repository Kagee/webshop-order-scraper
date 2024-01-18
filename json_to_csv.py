#!/usr/bin/env python3
from bootstrap import python_checks

python_checks()
# ruff: noqa: E402
from scrapers import settings

import csv
import sys
import argparse
from pathlib import Path
from scrapers.base import BaseScraper
from datetime import datetime

import logging.config

logging.config.dictConfig(settings.LOGGING)
log = logging.getLogger("json_to_csv")
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

    parser.add_argument(
        "--after",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        help="only export order after this date (default 1970-01-01)",
        default="1970-01-01",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
    )

    parser.add_argument(
        "--before",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        help="only export order before this date (default 3070-01-01)",
        default="3070-01-01",
    )

    subparsers = parser.add_subparsers(
        title="sources",
        description="valid sources",
        help="what shop to make csv for",
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
    shop = (
        shop_json["metadata"]["name"]
        if shop_json["metadata"]["name"] == shop_json["metadata"]["branch_name"]
        else shop_json["metadata"]["branch_name"]
    )
    log.info(f"Shop: {shop}")
    output = {}

    for order in shop_json["orders"]:
        date = datetime.strptime(order["date"], "%Y-%m-%d")
        if date > args.after and date < args.before:
            if order["date"] not in output:
                output[order["date"]] = []

            output[order["date"]].append(  [
                        order["date"],
                        order["id"],
                        order["subtotal"]["value"] if "subtotal" in order else "",
                        order["subtotal"]["currency"] if "subtotal" in order and "currency" in order["subtotal"] else "",
                        order["shipping"]["value"] if "shipping" in order else "",
                        order["shipping"]["currency"] if "shipping" in order and "currency" in order["shipping"] else "",
                        order["tax"]["value"] if "tax" in order else "",
                        order["tax"]["currency"] if "tax" in order and "currency" in order["tax"] else "",
                        order["total"]["value"],
                        order["total"]["currency"],
                        "",
                        "",
                        "",
                        "",
                        "",
                    ])
            for item in order["items"]:
                output[order["date"]].append(
                    [
                        order["date"],
                        order["id"],
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        item["name"],
                        (
                            item["variation"] if "variation" in item else ""
                        ),
                        item["quantity"],
                        item["total"]["value"] if "total" in item else "",
                        item["total"]["currency"] if "total" in item else "",
                    ]
                )

    with open(Path(settings.OUTPUT_FOLDER) / Path(args.source + ".csv"), 'w', newline='', encoding='utf-8') as csvfile:
        if args.stdout:
            out = sys.stdout
        else:
            out = csvfile
        writer = csv.writer(out, dialect=csv.excel)
        writer.writerow(
            [
                "order_date",
                "order_id",
                "subtotal",
                "subtotal_currency",
                "shipping",
                "shipping_currency",
                "tax",
                "tax_currency",
                "total",
                "total_currency",
                "item_name",
                "item_variation",
                "item_quantity",
                "item_value",
                "item_currency",
            ]
        )
        for sorted_date in dict(sorted(output.items())).values():
            for order in sorted_date:
                writer.writerow(order)


if __name__ == "__main__":
    main()
