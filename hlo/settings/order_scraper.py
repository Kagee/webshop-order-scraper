import os
import os.path
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .django import env

SCRAPER_CACHE_BASE: str = Path(env('SCRAPER_CACHE_BASE', default='./scraper-cache')).resolve()

_DEFAULT_PRINTER = "Microsoft Print to PDF" if os.name == "nt" else "Mozilla Save to PDF"
SCRAPER_PDF_PRINTER: str = env('SCRAPER_PDF_PRINTER', default=_DEFAULT_PRINTER)

SCRAPER_ALI_USERNAME: str = env('SCRAPER_ALI_USERNAME', default=None)
SCRAPER_ALI_PASSWORD: str = env('SCRAPER_ALI_PASSWORD', default=None)
SCRAPER_ALI_PASSWORD: str = env('SCRAPER_ALI_PASSWORD', default=None)
SCRAPER_ALI_ORDERS = env.list('SCRAPER_ALI_ORDERS', default=[])
SCRAPER_ALI_ORDERS_SKIP = env.list('SCRAPER_ALI_ORDERS_SKIP', default=[])
SCRAPER_ALI_ORDERS_MAX: int = env('SCRAPER_ALI_ORDERS_MAX', default=-1)
