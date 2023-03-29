import os
import os.path
from django.core.exceptions import ImproperlyConfigured
from pathlib import Path
from .django import env

SCRAPER_ALI_USERNAME: str = env('SCRAPER_ALI_USERNAME', default=None)
SCRAPER_ALI_PASSWORD: str = env('SCRAPER_ALI_PASSWORD', default=None)

_testPath = Path(env('SCRAPER_CACHE_BASE', default='./scraper-cache')).resolve()

if not os.access(_testPath, os.W_OK):
    raise ImproperlyConfigured(f"SCRAPER_CACHE_BASE is missing or not writeable: {_testPath}")

SCRAPER_CACHE_BASE: str = _testPath

_default_printer = "Microsoft Print to PDF" if os.name == "nt" else "Mozilla Save to PDF"
SCRAPER_PDF_PRINTER: str = env('SCRAPER_PDF_PRINTER', default=_default_printer)

SCRAPER_ALI_PASSWORD: str = env('SCRAPER_ALI_PASSWORD', default=None)
SCRAPER_ALI_ORDERS = env.list('SCRAPER_ALI_ORDERS', default=[])