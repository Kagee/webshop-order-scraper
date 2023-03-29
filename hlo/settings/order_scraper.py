import os
import os.path
from django.core.exceptions import ImproperlyConfigured
from .django import env

SCRAPER_ALI_USERNAME: str = env('SCRAPER_ALI_USERNAME', default=None)
SCRAPER_ALI_PASSWORD: str = env('SCRAPER_ALI_PASSWORD', default=None)

if not os.access(os.path.abspath(env('SCRAPER_CACHE', default='./scraper-cache')), os.W_OK):
    raise ImproperlyConfigured("SCRAPER_CACHE is missing or not writeable")

SCRAPER_CACHE: str = os.path.abspath(env('SCRAPER_CACHE', default='./scraper-cache'))
