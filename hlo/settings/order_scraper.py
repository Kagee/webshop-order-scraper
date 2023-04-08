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
SCRAPER_ALI_MANUAL_LOGIN = env.bool('SCRAPER_ALI_MANUAL_LOGIN', False)
SCRAPER_ALI_USERNAME: str = env('SCRAPER_ALI_USERNAME', default=None)
SCRAPER_ALI_PASSWORD: str = env('SCRAPER_ALI_PASSWORD', default=None)
SCRAPER_ALI_ORDERS = [x.strip() for x in env.list('SCRAPER_ALI_ORDERS', default=[])]
SCRAPER_ALI_ORDERS_SKIP = [x.strip() for x in env.list('SCRAPER_ALI_ORDERS_SKIP', default=[])]
SCRAPER_ALI_ORDERS_MAX: int = env('SCRAPER_ALI_ORDERS_MAX', default=-1)


# Config for scraper amazon command
SCRAPER_AMZ_MANUAL_LOGIN = env.bool('SCRAPER_AMZ_MANUAL_LOGIN', False)
SCRAPER_AMZ_USERNAME: str = env('SCRAPER_AMZ_USERNAME', default=None)
SCRAPER_AMZ_PASSWORD: str = env('SCRAPER_AMZ_PASSWORD', default=None)
SCRAPER_AMZ_ORDERS_MAX: int = env('SCRAPER_AMZ_ORDERS_MAX', default=-1)
# Format: SCRAPER_AMZ_ORDERS=com=123;456,co.jp=789
SCRAPER_AMZ_ORDERS = {
    key:[x.strip() for x in value.split(';')] \
        for (key,value) in \
            env.dict('SCRAPER_AMZ_ORDERS', default={}).items() \
                  }
# Strip any whitespace
SCRAPER_AMZ_ORDERS_SKIP = [x.strip() for x in env.list('SCRAPER_AMZ_ORDERS_SKIP', default=[])]


# Config for scraper dec command
SCRAPER_DEC_MANUAL_LOGIN = env.bool('SCRAPER_DEC_MANUAL_LOGIN', False)
SCRAPER_DEC_USERNAME: str = env('SCRAPER_DEC_USERNAME', default=None)
SCRAPER_DEC_PASSWORD: str = env('SCRAPER_DEC_PASSWORD', default=None)
