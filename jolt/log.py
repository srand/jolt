from __future__ import print_function
import os
import sys
import tqdm
import traceback
from datetime import datetime

from jolt import config
from jolt import filesystem as fs
from jolt import colors


_stdout = os.fdopen(os.dup(sys.__stdout__.fileno()), "w")
_stderr = os.fdopen(os.dup(sys.__stderr__.fileno()), "w")


ERROR = 0
WARN = 1
NORMAL = 2
VERBOSE = 3
HYSTERICAL = 4

_levelstr = ["ERROR", "WARNING", "INFO", "VERBOSE", "HYSTERICAL"]

default_path = fs.path.join(fs.path.expanduser("~"), ".jolt", "jolt.log")
path = config.get("jolt", "logfile", default_path)

_loglevel = NORMAL
try:
    dirpath = fs.path.dirname(path)
    if not fs.path.exists(dirpath):
        fs.makedirs(dirpath)
    _file = open(path, "a")
except:
    print("[ERROR] " + colors.red("could not open logfile: {0}".format(path)))
    print("[ERROR] " + colors.red("please set 'jolt.logfile' to an alternate path"))
    sys.exit(1)


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

def _streamwrite_file(stream, line):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    _streamwrite(stream, ts + " " + line)

def _log(level, stream, fmt, *args, **kwargs):
    line = _line(level, fmt, *args, **kwargs)
    if level <= _loglevel:
        _streamwrite(stream, line)
    _streamwrite_file(_file, line)

def set_level(level):
    global _loglevel
    _loglevel = level

def info(fmt, *args, **kwargs):
    _log(NORMAL, _stdout, fmt, *args, **kwargs)

def warn(fmt, *args, **kwargs):
    _log(WARN, _stdout, colors.yellow(fmt), *args, **kwargs)

def verbose(fmt, *args, **kwargs):
    _log(VERBOSE, _stdout, fmt, *args, **kwargs)

def hysterical(fmt, *args, **kwargs):
    _log(HYSTERICAL, _stdout, fmt, *args, **kwargs)

def error(fmt, *args, **kwargs):
    _log(ERROR, _stdout, colors.red(fmt), *args, **kwargs)

def exception(exc=None):
    if exc:
        _streamwrite(_stderr, "[ERROR] " + colors.red(str(exc)))
        _streamwrite_file(_file, "[ERROR] " + str(exc))
    backtrace = traceback.format_exc()
    for line in backtrace.splitlines():
        _streamwrite_file(_file, "[ERROR] " + line)

def stdout(fmt, *args, **kwargs):
    try:
        line = utils.expand(fmt, *args, ignore_errors=True, **kwargs)
    except:
        line = fmt
    _streamwrite(_stdout, _prefix(None, **kwargs) + line)
    _streamwrite_file(_file, _prefix("STDOUT", **kwargs) + line)

def stderr(fmt, *args, **kwargs):
    try:
        line = utils.expand(fmt, *args, ignore_errors=True, **kwargs)
    except:
        line = fmt
    _streamwrite(_stderr, line)
    _streamwrite_file(_file, "[STDERR] " + line)

def progress(desc, count, unit):
    _streamwrite_file(_file, "[INFO] " + desc)
    p = tqdm.tqdm(total=count, unit=unit, unit_scale=True)
    p.set_description(desc)
    return p


_file.write("================================================================================\n")
_file.flush()
