from __future__ import print_function
import sys
import tqdm
import traceback

from jolt import config
from jolt import filesystem as fs
from jolt import colors

ERROR = 0
WARN = 1
NORMAL = 2
VERBOSE = 3
HYSTERICAL = 4

_levelstr = ["ERROR", "WARNING", "INFO", "VERBOSE", "HYSTERICAL"]

path = config.get("jolt", "logfile", fs.path.join(fs.path.dirname(__file__), "jolt.log"))

_loglevel = NORMAL
_file = open(path, "a")

def _prefix(level, **kwargs):
    if type(level) == int:
        level = "[{}]".format(_levelstr[level])
    elif type(level) == str:
        level = "[{}]".format(level)
    else:
        level = ""
    context = kwargs.get("log_context")
    context = "[{}]".format(context) if context else ""
    pad = " " if level and context else ""
    return context + pad + level + " "

def _line(level, fmt, *args, **kwargs):
    from jolt.utils import expand
    return _prefix(level, **kwargs) + expand(fmt, *args, ignore_errors=True, **kwargs)

def _streamwrite(stream, line):
    stream.write(line + "\r\n")
    stream.flush()

def _log(level, stream, fmt, *args, **kwargs):
    line = _line(level, fmt, *args, **kwargs)
    if level <= _loglevel:
        _streamwrite(stream, line)
    _streamwrite(_file, line)

def set_level(level):
    global _loglevel
    _loglevel = level

def info(fmt, *args, **kwargs):
    _log(NORMAL, sys.stdout, fmt, *args, **kwargs)

def warn(fmt, *args, **kwargs):
    _log(WARN, sys.stdout, colors.yellow(fmt), *args, **kwargs)

def verbose(fmt, *args, **kwargs):
    _log(VERBOSE, sys.stdout, fmt, *args, **kwargs)

def hysterical(fmt, *args, **kwargs):
    _log(HYSTERICAL, sys.stdout, fmt, *args, **kwargs)

def error(fmt, *args, **kwargs):
    _log(ERROR, sys.stdout, colors.red(fmt), *args, **kwargs)

def exception(exc=None):
    if exc:
        _streamwrite(sys.stderr, "[ERROR] " + colors.red(str(exc)))
        _streamwrite(_file, "[ERROR] " + str(exc))
    backtrace = traceback.format_exc()
    for line in backtrace.splitlines():
        _streamwrite(_file, "[ERROR] " + line)

def stdout(fmt, *args, **kwargs):
    try:
        line = utils.expand(fmt, *args, ignore_errors=True, **kwargs)
    except:
        line = fmt
    _streamwrite(sys.stdout, _prefix(None, **kwargs) + line)
    _streamwrite(_file, _prefix("STDOUT", **kwargs) + line)

def stderr(fmt, *args, **kwargs):
    try:
        line = utils.expand(fmt, *args, ignore_errors=True, **kwargs)
    except:
        line = fmt
    _streamwrite(sys.stderr, line)
    _streamwrite(_file, "[STDERR] " + line)

def progress(desc, count, unit):
    _streamwrite(_file, "[INFO] " + desc)
    p = tqdm.tqdm(total=count, unit=unit, unit_scale=True)
    p.set_description(desc)
    return p


_file.write("================================================================================\n")
_file.flush()
