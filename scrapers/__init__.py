from .adafruit import AdafruitScraper
from .aliexpress import AliExpressScraper
from .amazon import AmazonScraper
from .base import BaseScraper, PagePart
from .digikey import DigikeyScraper
from .distrelec import DistrelecScraper
from .ebay import EbayScraper
from .imap import IMAPScraper
from .jula import JulaScraper
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
    "JulaScraper",
    "DistrelecScraper",
    "DigikeyScraper",
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
