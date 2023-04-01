import os
import os.path
from pathlib import Path

from .django import env

# Config for scraper command
SCRAPER_CACHE_BASE: str = Path(env('SCRAPER_CACHE_BASE', default='./scraper-cache')).resolve()
SCRAPER_PDF_PRINTER: str = env(
    'SCRAPER_PDF_PRINTER',
    default="Microsoft Print to PDF" if os.name == "nt" else "Mozilla Save to PDF")

# Config for scraper aliexpress command
SCRAPER_ALI_USERNAME: str = env('SCRAPER_ALI_USERNAME', default=None)
SCRAPER_ALI_PASSWORD: str = env('SCRAPER_ALI_PASSWORD', default=None)
SCRAPER_ALI_ORDERS = env.list('SCRAPER_ALI_ORDERS', default=[])
SCRAPER_ALI_ORDERS_SKIP = env.list('SCRAPER_ALI_ORDERS_SKIP', default=[])
SCRAPER_ALI_ORDERS_MAX: int = env('SCRAPER_ALI_ORDERS_MAX', default=-1)

# Config for scraper amazon.de command
SCRAPER_AMZDE_USERNAME: str = env('SCRAPER_AMZDE_USERNAME', default=None)
SCRAPER_AMZDE_PASSWORD: str = env('SCRAPER_AMZDE_PASSWORD', default=None)
SCRAPER_AMZDE_ORDERS_MAX: int = env('SCRAPER_AMZDE_ORDERS_MAX', default=-1)
SCRAPER_AMZDE_ORDERS = env.list('SCRAPER_AMZDE_ORDERS_SKIP', default=[])
SCRAPER_AMZDE_ORDERS_SKIP = env.list('SCRAPER_AMZDE_ORDERS_SKIP', default=[])
