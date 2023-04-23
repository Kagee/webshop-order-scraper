import os
import os.path
from pathlib import Path

from environs import Env

env = Env()
with env.prefixed("WS_"):
    env.read_env()

    LOGGING = {
        "version": 1,
        "formatters": {
            "verbose": {
                "format": "{asctime} [{levelname}] {module}: {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
            "file": {
                "class": "logging.FileHandler",
                "filename": "scraper.log",
                "formatter": "verbose",
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "scraper": {
                "handlers": ["console"],
                "level": "WARNING",
            },
            "scrapers": {
                "handlers": ["console"],
                "level": "INFO",
            },
        },
    }

    CACHE_BASE: Path = Path(
        env("CACHE_BASE", default="./scraper-cache")
    ).resolve()
    PDF_PRINTER: str = env(
        "PDF_PRINTER",
        default=(
            "Microsoft Print to PDF"
            if os.name == "nt"
            else "Mozilla Save to PDF"
        ),
    )
    EXPORT_FOLDER: Path = Path(
        env("EXPORT_FOLDER", default="./output")
    ).resolve()

    NO_COLOR: str = env.bool(
        "NO_COLOR",
        default=False,
    )

    # Config for scraper aliexpress command
    ALI_MANUAL_LOGIN = env.bool("ALI_MANUAL_LOGIN", default=False)
    ALI_USERNAME: str = env("ALI_USERNAME", default=None)
    ALI_PASSWORD: str = env("ALI_PASSWORD", default=None)
    ALI_ORDERS = [x.strip() for x in env.list("ALI_ORDERS", default=[])]
    ALI_ORDERS_SKIP = [
        x.strip() for x in env.list("ALI_ORDERS_SKIP", default=[])
    ]
    ALI_ORDERS_MAX: int = env.int("ALI_ORDERS_MAX", default=-1)

    # Config for scraper amazon command
    AMZ_MANUAL_LOGIN = env.bool("AMZ_MANUAL_LOGIN", default=False)
    AMZ_USERNAME: str = env("AMZ_USERNAME", default=None)
    AMZ_PASSWORD: str = env("AMZ_PASSWORD", default=None)
    AMZ_ORDERS_MAX: int = env.int("AMZ_ORDERS_MAX", default=-1)
    # Format: AMZ_ORDERS=com=123;456,co.jp=789
    AMZ_ORDERS = {
        key: [x.strip() for x in value.split(";")]
        for (key, value) in env.dict("AMZ_ORDERS", default={}).items()
    }
    # Strip any whitespace
    AMZ_ORDERS_SKIP = [
        x.strip() for x in env.list("AMZ_ORDERS_SKIP", default=[])
    ]

    # Config for scraper dec command
    DEC_MANUAL_LOGIN = env.bool("DEC_MANUAL_LOGIN", default=False)
    DEC_USERNAME: str = env("DEC_USERNAME", default=None)
    DEC_PASSWORD: str = env("DEC_PASSWORD", default=None)

    # Config for scraper adafruit command
    ADA_ITEMS_MAX: int = env("ADA_ITEMS_MAX", default=-1)
    ADA_ITEMS = [x.strip() for x in env.list("ADA_ITEMS", default=[])]

    EBY_MANUAL_LOGIN = env.bool("EBY_MANUAL_LOGIN", default=False)
    EBY_USERNAME: str = env("EBY_USERNAME", default=None)
    EBY_PASSWORD: str = env("EBY_PASSWORD", default=None)
    EBY_ORDERS_MAX: int = env.int("EBY_ORDERS_MAX", default=-1)
    # Format: EBY_ORDERS=order_id|order_trans_id-order_item_id
    #                            [,order_id|order_trans_id-order_item_id]
    EBY_ORDERS = {x.strip() for x in env.list("EBY_ORDERS", default=[])}
    # Strip any whitespace
    EBY_ORDERS_SKIP = [
        x.strip() for x in env.list("EBY_ORDERS_SKIP", default=[])
    ]

    PIM_MANUAL_LOGIN = env.bool("PIM_MANUAL_LOGIN", default=False)
    PIM_USERNAME: str = env("PIM_USERNAME", default=None)
    PIM_PASSWORD: str = env("PIM_PASSWORD", default=None)
    PIM_ORDERS_MAX: int = env.int("PIM_ORDERS_MAX", default=-1)
    PIM_ORDERS = {x.strip() for x in env.list("PIM_ORDERS", default=[])}
    PIM_ORDERS_SKIP = [
        x.strip() for x in env.list("PIM_ORDERS_SKIP", default=[])
    ]

    IMAP_SERVER: str = env("IMAP_SERVER", default="imap.gmail.com")
    IMAP_PORT: int = env.int("IMAP_PORT", default=993)
    IMAP_USERNAME: str = env("IMAP_USERNAME", default=None)
    IMAP_PASSWORD: str = env("IMAP_PASSWORD", default=None)
    # We use this flag to find the localized Gmail "All Main" folder
    IMAP_FLAGS: list = env.list("IMAP_FLAGS", default=[])
    IMAP_FOLDERS: list = env.list("IMAP_FOLDERS", default=[])
