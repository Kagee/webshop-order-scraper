#!/usr/bin/env python3
from bootstrap import python_checks

python_checks()
# ruff: noqa: E402
import argparse
import csv
import datetime as dt
import decimal
import logging.config
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from scrapers import settings
from scrapers.base import BaseScraper

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
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").astimezone(),
        help="only export order after this date (default 1970-01-01)",
        default="1970-01-01",
    )

    parser.add_argument(
        "--delimiter",
        type=str,
        help="delimiter in csv. Default is based on excel dialect.",
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
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").astimezone(),
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


def main():  # noqa: PLR0915, C901
    args = parse_args()

    conv_data = {}

    if not args.nok:

        def convert_to_nok(value, _conv, _mult):
            return str(value)

        def curr_to_nok(curr):
            return str(curr)

    else:

        def convert_to_nok(value, curr, date):
            if value == "" or curr in ["", "NOK"]:
                return str(value)

            value = Decimal(value.replace(",", "."))
            conv = Decimal(conv_data[curr][date]["value"].replace(",", "."))
            mult = conv_data[curr][date]["mult"]

            if mult == "0":
                return str(
                    (value * conv).quantize(
                        decimal.Decimal(".00"),
                        decimal.ROUND_HALF_UP,
                    ),
                )
            if mult == "2":
                return str(
                    ((value * conv) / 100).quantize(
                        decimal.Decimal(".00"),
                        decimal.ROUND_HALF_UP,
                    ),
                )
            msg = f"Unexpected mult: {mult}"
            raise ValueError(msg)

        def curr_to_nok(_):
            return "NOK"

        exr_msg = (
            'Download "Alle valutakurser - Daglige kurser - Siste 10 år"'
            " from"
            " https://www.norges-bank.no/tema/Statistikk/Valutakurser/?tab=api"
            " and save as EXR.csv"
        )
        if not Path("EXR.csv").is_file():
            log.error(exr_msg)
            sys.exit(1)
        log.info("Loading EXR.csv, this may take some time...")
        with Path("EXR.csv").open(newline="", encoding="utf-8-sig") as csvfile:
            oldest_date_in_exr = datetime.strptime(
                "1970-01-01",
                "%Y-%m-%d",
            ).astimezone()
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                date = datetime.strptime(
                    row["TIME_PERIOD"],
                    "%Y-%m-%d",
                ).astimezone()
                if date > oldest_date_in_exr:
                    oldest_date_in_exr = date
            today = datetime.now().astimezone()
            days_old = (today - oldest_date_in_exr).days
            log.debug(
                "Oldest date in EXR.csv is %s, %s days old",
                oldest_date_in_exr,
                days_old,
            )
        with Path("EXR.csv").open(newline="", encoding="utf-8-sig") as csvfile:
            prev_base = None
            prev_mult = None
            prev_date = None
            prev_value = None
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                if prev_base and prev_base != row["BASE_CUR"]:
                    # We have switched to a new currency
                    # Reset all previous values
                    prev_mult = None
                    prev_date = None
                    prev_value = None
                date = datetime.strptime(
                    row["TIME_PERIOD"],
                    "%Y-%m-%d",
                ).astimezone()
                if prev_date:
                    # We are only here if prev_base = base
                    exp_date = prev_date + dt.timedelta(days=1)
                    if date != exp_date:
                        # We got date, but expected exp_date
                        while True:
                            try:
                                prev_date += dt.timedelta(days=1)
                            except OverflowError:
                                msg = (
                                    "This should not happen, we overflowed "
                                    "while generating intermediate "
                                    "exchange rates: %s %s %s"
                                )
                                log.exception(
                                    msg,
                                    prev_date,
                                    exp_date,
                                    oldest_date_in_exr,
                                )
                                raise

                            if date == prev_date:
                                # The current prev_date is the date we
                                # read in this row, do not generate anymore
                                break

                            if prev_date > oldest_date_in_exr:
                                # The generated date is higher than the highest
                                # overall date from the input file
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
    log.info("Shop: %s", shop)
    output = {}

    for order in shop_json["orders"]:
        date = datetime.strptime(order["date"], "%Y-%m-%d").astimezone()
        if date > args.after and date < args.before:
            if args.nok and date > oldest_date_in_exr:
                log.error(
                    (
                        "Order with date %s is older than latest"
                        " date in EXR.csv %s, can not calculate"
                    ),
                    date,
                    oldest_date_in_exr,
                )
                sys.exit(1)
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
                ],
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
                    ],
                )

    with (Path(settings.OUTPUT_FOLDER) / Path(args.source + ".csv")).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
        out = sys.stdout if args.stdout else csvfile
        options = {}
        if args.delimiter:
            options["delimiter"] = args.delimiter
        writer = csv.writer(out, dialect=csv.excel, **options)
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
            ],
        )
        for sorted_date in dict(sorted(output.items())).values():
            for order in sorted_date:
                writer.writerow(order)


if __name__ == "__main__":
    main()
