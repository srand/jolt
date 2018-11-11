from __future__ import print_function
import sys
import config
import filesystem as fs
import tqdm
import utils


ERROR = 0
WARN = 1
NORMAL = 2
VERBOSE = 3
HYSTERICAL = 4

path = config.get("jolt", "logfile", fs.path.join(fs.path.dirname(__file__), "jolt.log"))

_loglevel = NORMAL
_file = open(path, "a")

def _line(level, fmt, *args, **kwargs):
    levelstr = ["ERROR", "WARNING", "INFO", "VERBOSE", "HYSTERICAL"]
    return "[{}] ".format(levelstr[level]) + \
        utils.expand(fmt, *args, ignore_errors=True, **kwargs)

def _streamwrite(stream, line):
    stream.write(line + "\n")
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
    _log(WARN, sys.stdout, fmt, *args, **kwargs)

def verbose(fmt, *args, **kwargs):
    _log(VERBOSE, sys.stdout, fmt, *args, **kwargs)

def hysterical(fmt, *args, **kwargs):
    _log(HYSTERICAL, sys.stdout, fmt, *args, **kwargs)

def error(fmt, *args, **kwargs):
    _log(ERROR, sys.stdout, fmt, *args, **kwargs)

def stdout(fmt, *args, **kwargs):
    try:
        line = utils.expand(fmt, *args, ignore_errors=True, **kwargs)
    except:
        line = fmt
    _streamwrite(sys.stdout, line)
    _streamwrite(_file, "[STDOUT] " + line)

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
