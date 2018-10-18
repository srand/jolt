from __future__ import print_function
import sys


ERROR = 0
NORMAL = 1
VERBOSE = 2
HYSTERICAL = 3


_loglevel = NORMAL


def set_level(level):
    global _loglevel
    _loglevel = level

def info(fmt, *args, **kwargs):
    if _loglevel >= NORMAL:
        sys.stdout.write("[INFO]  " + fmt.format(*args, **kwargs) + "\n")
        sys.stdout.flush()

def verbose(fmt, *args, **kwargs):
    if _loglevel >= VERBOSE:
        print("[VERBOSE] "+ fmt.format(*args, **kwargs))

def hysterical(fmt, *args, **kwargs):
    if _loglevel >= HYSTERICAL:
        print("[HYSTERICAL] "+ fmt.format(*args, **kwargs))

def error(fmt, *args, **kwargs):
    print("[ERROR] "+ fmt.format(*args, **kwargs))

def eprint(fmt, *args, **kwargs):
    print("error: " + fmt.format(*args, **kwargs), file=sys.stderr)
