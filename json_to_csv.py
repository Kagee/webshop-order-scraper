#!/usr/bin/env python3
from bootstrap import python_checks

python_checks()
# ruff: noqa: E402
from scrapers import settings

import csv
import sys
import argparse
import decimal
from decimal import Decimal
from pathlib import Path
from scrapers.base import BaseScraper
import datetime as dt
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
        "--nok",
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

    conv_data = {}

    if not args.nok:

        def convert_to_nok(value, conv, mult):
            return str(value)

        def curr_to_nok(curr):
            return str(curr)

    else:

        def convert_to_nok(value, curr, date):
            if value == "" or curr == "":
                return str(value)

            value = Decimal(value.replace(",", "."))
            conv = Decimal(conv_data[curr][date]["value"].replace(",", "."))
            mult = conv_data[curr][date]["mult"]

            if mult == "0":
                return str(
                    (value * conv).quantize(
                        decimal.Decimal(".00"), decimal.ROUND_HALF_UP
                    )
                )
            elif mult == "2":
                return str(
                    ((value * conv) / 100).quantize(
                        decimal.Decimal(".00"), decimal.ROUND_HALF_UP
                    )
                )
            raise ValueError(f"Unexpected mult: {mult}")

        def curr_to_nok(curr):
            return str("NOK")

        if not Path("EXR.csv").is_file():
            log.error(
                'Download "Alle valutakurser - Daglige kurser - Siste 10 år"'
                " from"
                " https://www.norges-bank.no/tema/Statistikk/Valutakurser/?tab=api"
                " and save as EXR.csv"
            )
            sys.exit(1)
        log.info("Loading EXR.csv, this may take some time...")
        with Path("EXR.csv").open(newline="", encoding="utf-8-sig") as csvfile:
            prev_base = None
            # prev_quote = None
            prev_mult = None
            prev_date = None
            prev_value = None
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                if prev_base and prev_base != row["BASE_CUR"]:
                    # prev_quote = None
                    prev_mult = None
                    prev_date = None
                    prev_value = None
                date = datetime.strptime(row["TIME_PERIOD"], "%Y-%m-%d")
                if prev_date:
                    exp_date = prev_date + dt.timedelta(days=1)
                    if date != exp_date:
                        while True:
                            prev_date += dt.timedelta(days=1)
                            if date == prev_date:
                                break
                            if row["BASE_CUR"] not in conv_data:
                                conv_data[row["BASE_CUR"]] = {}
                            conv_data[row["BASE_CUR"]][
                                prev_date.strftime("%Y-%m-%d")
                            ] = {
                                "mult": prev_mult,
                                "value": prev_value,
                            }
                if row["BASE_CUR"] not in conv_data:
                    conv_data[row["BASE_CUR"]] = {}
                conv_data[row["BASE_CUR"]][date.strftime("%Y-%m-%d")] = {
                    "mult": row["UNIT_MULT"],
                    "value": row["OBS_VALUE"],
                }
                prev_base = row["BASE_CUR"]
                # prev_quote = row["QUOTE_CUR"]
                prev_mult = row["UNIT_MULT"]
                prev_date = date
                prev_value = row["OBS_VALUE"]

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
            # convert_to_nok(value, curr, date) curr_to_nok
            output[order["date"]].append(
                [
                    order["date"],
                    order["id"],
                    (
                        convert_to_nok(
                            order["subtotal"]["value"],
                            (
                                order["subtotal"]["currency"]
                                if "currency" in order["subtotal"]
                                else ""
                            ),
                            order["date"],
                        )
                        if "subtotal" in order
                        else ""
                    ),
                    (
                        curr_to_nok(order["subtotal"]["currency"])
                        if "subtotal" in order
                        and "currency" in order["subtotal"]
                        else ""
                    ),
                    (
                        convert_to_nok(
                            order["shipping"]["value"],
                            (
                                order["shipping"]["currency"]
                                if "currency" in order["shipping"]
                                else ""
                            ),
                            order["date"],
                        )
                        if "shipping" in order
                        else ""
                    ),
                    (
                        curr_to_nok(order["shipping"]["currency"])
                        if "shipping" in order
                        and "currency" in order["shipping"]
                        else ""
                    ),
                    (
                        convert_to_nok(
                            order["tax"]["value"],
                            (
                                order["tax"]["currency"]
                                if "currency" in order["tax"]
                                else ""
                            ),
                            order["date"],
                        )
                        if "tax" in order
                        else ""
                    ),
                    (
                        curr_to_nok(order["tax"]["currency"])
                        if "tax" in order and "currency" in order["tax"]
                        else ""
                    ),
                    convert_to_nok(
                        order["total"]["value"],
                        (
                            order["total"]["currency"]
                            if "currency" in order["total"]
                            else ""
                        ),
                        order["date"],
                    ),
                    curr_to_nok(order["total"]["currency"]),
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
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
                        (item["variation"] if "variation" in item else ""),
                        item["quantity"],
                        (
                            convert_to_nok(
                                item["total"]["value"],
                                (
                                    item["total"]["currency"]
                                    if "currency" in order["total"]
                                    else ""
                                ),
                                order["date"],
                            )
                            if "total" in item
                            else ""
                        ),
                        (
                            curr_to_nok(item["total"]["currency"])
                            if "total" in item
                            else ""
                        ),
                    ]
                )

    with open(
        Path(settings.OUTPUT_FOLDER) / Path(args.source + ".csv"),
        "w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
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
