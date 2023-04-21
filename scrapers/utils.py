import colored
from colored import stylize
from . import settings

# pylint: disable=invalid-name


def RED(msg):
    return stylize(msg, colored.fg("red")) if not settings.NO_COLOR else msg


def AMBER(msg):
    return (
        stylize(msg, colored.fg("dark_orange"))
        if not settings.NO_COLOR
        else msg
    )


def GREEN(msg):
    return stylize(msg, colored.fg("green")) if not settings.NO_COLOR else msg


def BLUE(msg):
    return stylize(msg, colored.fg("blue_3a")) if not settings.NO_COLOR else msg
