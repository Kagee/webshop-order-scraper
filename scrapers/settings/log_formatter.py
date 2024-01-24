import logging

from colored import (  # noqa: F401
    Back,
    Fore,
    Style,
    back,
    fore,
    style,
    stylize,
)

from scrapers.utils import *  # noqa: F403


# Custom formatter
class LogFormatter(logging.Formatter):
    # https://dslackw.gitlab.io/colored/tables/colors/
    error_fmt = (
        f"{fore('red')}%(asctime)s [%(levelname)s] "
        f"%(module)s:%(funcName)s: %(message)s{Style.reset}"
    )
    warning_fmt = (
        f"{fore('dark_orange')}%(asctime)s [%(levelname)s] "
        f"%(module)s:%(funcName)s: %(message)s{Style.reset}"
    )
    info_fmt = (
        f"{Style.reset}%(asctime)s [%(levelname)s] "
        f"%(module)s:%(funcName)s: %(message)s{Style.reset}"
    )
    debug_fmt = (
        f"{fore('dark_gray')}%(asctime)s [%(levelname)s] "
        f"%(module)s:%(funcName)s: %(message)s{Style.reset}"
    )

    def __init__(self):
        super().__init__(fmt="%(levelno)d: %(msg)s", datefmt=None, style="%")

    def format(self, record):
        # Save the original format configured by the user
        # when the logger formatter was instantiated
        format_orig = self._style._fmt  # noqa: SLF001

        # Replace the original format with one customized by logging level
        self._style._fmt = {  # noqa: SLF001
            logging.DEBUG: LogFormatter.debug_fmt,
            logging.INFO: LogFormatter.info_fmt,
            logging.WARNING: LogFormatter.warning_fmt,
            logging.ERROR: LogFormatter.error_fmt,
            logging.CRITICAL: LogFormatter.error_fmt,
        }[record.levelno]

        # Call the original formatter class to do the grunt work
        result = logging.Formatter.format(self, record)

        # Restore the original format configured by the user
        self._style._fmt = format_orig  # noqa: SLF001

        return result
