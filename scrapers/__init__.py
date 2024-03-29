from .adafruit import AdafruitScraper
from .aliexpress import AliExpressScraper
from .amazon import AmazonScraper
from .base import BaseScraper, PagePart
from .distrelec import DistrelecScraper
from .ebay import EbayScraper
from .imap import IMAPScraper
from .kjell import KjellScraper
from .komplett import KomplettScraper
from .pimoroni import PimoroniScraper
from .polyalkemi import PolyalkemiScraper
from .tindie import TindieScraper
from .utils import AMBER, BLUE, GREEN, RED

__all__ = [
    "AdafruitScraper",
    "AliExpressScraper",
    "AmazonScraper",
    "BaseScraper",
    "PagePart",
    "DistrelecScraper",
    "IMAPScraper",
    "PimoroniScraper",
    "EbayScraper",
    "KjellScraper",
    "PolyalkemiScraper",
    "KomplettScraper",
    "TindieScraper",
    "RED",
    "BLUE",
    "AMBER",
    "GREEN",
]
