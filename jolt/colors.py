import sys

from colorama import Fore, Style
from jolt import config


_tty = sys.stdout.isatty() and sys.stderr.isatty()


def enabled():
    return _tty and config.getboolean("jolt", "colors", True)


def red(s):
    return Fore.RED + Style.BRIGHT + s + Style.RESET_ALL if enabled() else s


def yellow(s):
    return Fore.YELLOW + Style.BRIGHT + s + Style.RESET_ALL if enabled() else s


def green(s):
    return Fore.GREEN + Style.BRIGHT + s + Style.RESET_ALL if enabled() else s


def blue(s):
    return Fore.BLUE + Style.BRIGHT + s + Style.RESET_ALL if enabled() else s


def bright(s):
    return Style.BRIGHT + s + Style.RESET_ALL if enabled() else s


def dim(s):
    return Style.DIM + s + Style.RESET_ALL if enabled() else s
