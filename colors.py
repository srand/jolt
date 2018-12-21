from colorama import Fore, Style
import config


enabled = config.getboolean("jolt", "colors", True)

def red(s):
    return Fore.RED + Style.BRIGHT + s + Style.RESET_ALL if enabled else s

def green(s):
    return Fore.GREEN + Style.BRIGHT + s + Style.RESET_ALL if enabled else s

def bright(s):
    return Style.BRIGHT + s + Style.RESET_ALL if enabled else s
