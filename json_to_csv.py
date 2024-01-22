#!/usr/bin/env python3
from bootstrap import python_checks

python_checks()
# ruff: noqa: E402
import argparse
import csv
import datetime as dt
import decimal
import logging.config
import shutil
import sys
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from scrapers import settings
from scrapers.base import BaseScraper

logging.config.dictConfig(settings.LOGGING)
log = logging.getLogger("json_to_csv")
log.debug("Base logging configured")

AFTER_YEAR_DEFAULT = 1970
BEFORE_YEAR_DEFAULT = 3070


def parse_args():
    log.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(
        description="Show stats per shop based on JSON export",
    )

    parser.add_argument(
        "--after",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").astimezone(),
        help="only export order after this date (default 1970-01-01)",
        default=f"{AFTER_YEAR_DEFAULT}-01-01",
    )

    parser.add_argument(
        "--before",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").astimezone(),
        help="only export order before this date (default 3070-01-01)",
        default=f"{BEFORE_YEAR_DEFAULT}-01-01",
    )

    parser.add_argument(
        "--delimiter",
        type=str,
        help=(
            "delimiter in csv. Default is based on excel "
            "dialect. Magic value TAB is supported."
        ),
    )

    parser.add_argument(
        "--separator",
        type=str,
        help="decimal separator. Default is ???",
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
        "--no-order-totals",
        action="store_true",
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


def check_or_download_exr(syear: int, eyear: int) -> list[Path]:
    eyear += 1
    url = (
        "https://data.norges-bank.no/api/data/EXR/B..NOK.SP?"
        "startPeriod={year}-01-22&"
        "endPeriod={year}-12-31&"
        "format=csv&bom=include&locale=no"
    )
    now = datetime.now().astimezone()
    curr_year = int(now.strftime("%Y"))
    last_year = curr_year - 1

    files = []
    for exr_year in range(syear, eyear):
        csv_file = settings.CACHE_BASE / f"EXR-{exr_year}.csv"
        files.append(csv_file)
        if not csv_file.is_file() or exr_year in [curr_year, last_year]:
            if exr_year == last_year and csv_file.is_file():
                last_year_modified = datetime.fromtimestamp(
                    csv_file.stat().st_mtime,
                ).astimezone()
                if last_year_modified.year == curr_year:
                    log.debug("Rates for %s found", exr_year)
                    continue
            log.debug("Downloading rate date for %s", exr_year)
            with urllib.request.urlopen(  # noqa: S310
                url.format(year=exr_year),
            ) as response, csv_file.open(
                "wb",
            ) as csv_handle:
                shutil.copyfileobj(response, csv_handle)
        else:
            log.debug("Rates for %s found", exr_year)
    return files


def calculate_year_range_currencies(args, orders) -> list[int, int, set[str]]:
    ystart: int = None
    yend: int = None
    currencies = set()
    if args.after and args.after.year != AFTER_YEAR_DEFAULT:
        ystart = args.after.year
    if args.before and args.before.year != BEFORE_YEAR_DEFAULT:
        yend = args.before.year
    if not ystart or not yend:
        for order in orders:
            for value in ["subtotal", "shipping", "tax", "total"]:
                if value in order and "currency" in order[value]:
                    currencies.add(order[value]["currency"])
            date = datetime.strptime(order["date"], "%Y-%m-%d").astimezone()
            if date > args.after and date < args.before:
                ystart = min(date.year, ystart if ystart else date.year)
                yend = max(date.year, yend if yend else date.year)
            for item in order["items"]:
                if "currency" in item["total"]:
                    currencies.add(item["total"]["currency"])
    return ystart, yend, currencies


def main():  # noqa: PLR0915, C901
    args = parse_args()

    if args.after > args.before:
        msg = (
            f"Argument --after ({args.after}) must "
            "be earlier than --before ({args.before})"
        )
        raise ValueError(msg)

    rate_data = {}

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

    if args.separator:

        def force_separator(value):
            value = str(value)
            if "." in value:
                return value.replace(".", args.separator)
            return value.replace(",", args.separator)
    else:

        def force_separator(value):
            return value

    if not args.nok:

        def convert_to_nok(value, _conv, _mult):
            return force_separator(str(value))

        def curr_to_nok(curr):
            return str(curr)

    else:

        def convert_to_nok(value, curr, date):
            if value == "" or curr in ["", "NOK"]:
                return force_separator(str(value))

            value = Decimal(value.replace(",", "."))
            conv = Decimal(rate_data[curr][date]["value"].replace(",", "."))
            mult = rate_data[curr][date]["mult"]

            if mult == "0":
                return force_separator(
                    str(
                        (value * conv).quantize(
                            decimal.Decimal(".00"),
                            decimal.ROUND_HALF_UP,
                        ),
                    ),
                )
            if mult == "2":
                return force_separator(
                    str(
                        ((value * conv) / 100).quantize(
                            decimal.Decimal(".00"),
                            decimal.ROUND_HALF_UP,
                        ),
                    ),
                )
            msg = f"Unexpected mult: {mult}"
            raise ValueError(msg)

        def curr_to_nok(_):
            return "NOK"

        ystart, yend, currencies = calculate_year_range_currencies(
            args,
            shop_json["orders"],
        )
        log.debug(
            "Year range (%s,%s), currencies: %s",
            ystart,
            yend,
            ",".join(currencies),
        )

        exr_files = check_or_download_exr(ystart, yend)

        log.info("Loading EXR CSVs, this may take some time...")

        for exr in exr_files:
            with exr.open(newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile, delimiter=";")
                for row in reader:
                    if row["BASE_CUR"] in currencies:
                        if row["BASE_CUR"] not in rate_data:
                            rate_data[row["BASE_CUR"]] = {}
                        rate_data[row["BASE_CUR"]][row["TIME_PERIOD"]] = {
                            "mult": row["UNIT_MULT"],
                            "value": row["OBS_VALUE"],
                        }

        cur: dict

        dend = min(
            datetime(yend, 12, 31).astimezone(),
            datetime.now().astimezone(),
        )

        # Loop over currencies in dict
        for cur in rate_data.copy():
            prev_mult = None
            prev_date = None
            prev_value = None
            log.debug("Processing %s", cur)
            # Loop over dates for currency
            for date_str in sorted(rate_data[cur].copy().keys()):
                date = datetime.strptime(
                    date_str,
                    "%Y-%m-%d",
                ).astimezone()
                if date > dend:
                    # Stop processing currency if date is after
                    # last required year
                    break
                if prev_date:
                    exp_date = prev_date + dt.timedelta(days=1)
                    # Look for "missing" dates
                    if date != exp_date:
                        # We got date, but expected exp_date
                        while True:
                            prev_date += dt.timedelta(days=1)
                            if prev_date > dend:
                                # Stop processing currency if date is after
                                # last required year
                                break

                            if date_str == prev_date:
                                # The current prev_date is the date we
                                # read in this row, do not generate anymore
                                break

                            # Add missing dates to original dict
                            rate_data[cur][prev_date.strftime("%Y-%m-%d")] = {
                                "mult": prev_mult,
                                "value": prev_value,
                            }
                prev_mult = rate_data[cur][date_str]["mult"]
                prev_date = date
                prev_value = rate_data[cur][date_str]["value"]

    for order in shop_json["orders"]:
        date_str = datetime.strptime(order["date"], "%Y-%m-%d").astimezone()
        if date_str > args.after and date_str < args.before:
            if order["date"] not in output:
                output[order["date"]] = []
            if not args.no_order_totals:
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
                        force_separator(item["quantity"]),
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
                        ("1" if "tax" in order else "0"),
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
            if args.delimiter == "TAB":
                options["delimiter"] = "\t"
            else:
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
                "order_has_tax",
            ],
        )
        for sorted_date in dict(sorted(output.items())).values():
            for order in sorted_date:
                writer.writerow(order)


if __name__ == "__main__":
    main()
