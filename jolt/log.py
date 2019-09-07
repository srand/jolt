from __future__ import print_function
import os
import sys
import tqdm
import traceback
from datetime import datetime
import threading
import logging
import logging.handlers
from contextlib import contextmanager
try:
    from StringIO import StringIO
except:
    from io import StringIO

from jolt import config
from jolt import filesystem as fs
from jolt import colors


default_path = fs.path.join(config.get_logpath(), "jolt.log")
logfile = config.get("jolt", "logfile", default_path)
logsize = config.getsize("jolt", "logsize", os.environ.get("JOLT_LOGSIZE", 10*1024**2))  # 10MiB
logcount = config.getint("jolt", "logcount", os.environ.get("JOLT_LOGCOUNT", 1))

dirpath = fs.path.dirname(logfile)
if not fs.path.exists(dirpath):
    fs.makedirs(dirpath)
with open(logfile, "a") as f:
    f.write("--------------------------------------------------------------------------------\n")

################################################################################

ERROR = logging.ERROR
WARNING = logging.WARNING
INFO = logging.INFO
VERBOSE = 15
DEBUG = logging.DEBUG
EXCEPTION = logging.DEBUG + 1
STDOUT = logging.INFO + 1
STDERR = logging.ERROR + 1
logging.addLevelName(VERBOSE, "VERBOSE")
logging.addLevelName(STDOUT, "STDOUT")
logging.addLevelName(STDERR, "STDERR")
logging.addLevelName(EXCEPTION, "EXCEPT")

logging.raiseExceptions = False


class Formatter(logging.Formatter):
    def __init__(self, fmt, *args, **kwargs):
        super(Formatter, self).__init__(*args, **kwargs)
        self.fmt = fmt

    def format(self, record):
        try:
            record.message = record.msg.format(*record.args)
        except:
            record.message = record.msg
        record.asctime = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")
        return self.fmt.format(
            levelname=record.levelname,
            message=record.message,
            asctime=record.asctime
        )


class ConsoleFormatter(logging.Formatter):
    def __init__(self, fmt, *args, **kwargs):
        super(ConsoleFormatter, self).__init__(*args, **kwargs)
        self.fmt = fmt

    def format(self, record):
        try:
            msg = record.msg.format(*record.args)
        except:
            msg = record.msg
        if sys.stdout.isatty() and sys.stderr.isatty():
            if record.levelno >= ERROR:
                msg = colors.red(msg)
            elif record.levelno >= WARNING:
                msg = colors.yellow(msg)
        record.message = msg
        record.asctime = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")
        return self.fmt.format(
            levelname=record.levelname,
            message=record.message,
            asctime=record.asctime
        )


class Filter(logging.Filter):
    def __init__(self, filterfn):
        self.filterfn = filterfn

    def filter(self, record):
        return self.filterfn(record)


# create logger
_logger = logging.getLogger('jolt')
_logger.setLevel(logging.DEBUG)

_console_formatter = ConsoleFormatter('[{levelname:>7}] {message}')

_stdout = logging.StreamHandler(sys.stdout)
_stdout.setLevel(INFO)
_stdout.setFormatter(_console_formatter)
_stdout.addFilter(Filter(lambda r: r.levelno < ERROR))

_stderr = logging.StreamHandler(sys.stderr)
_stderr.setLevel(INFO)
_stderr.setFormatter(_console_formatter)
_stderr.addFilter(Filter(lambda r: r.levelno >= ERROR))
_stderr.addFilter(Filter(lambda r: r.levelno != EXCEPTION))

_file = logging.handlers.RotatingFileHandler(logfile, maxBytes=logsize, backupCount=logcount)
_file.setLevel(logging.DEBUG)
_file_formatter = Formatter('{asctime} [{levelname:>7}] {message}')
_file.setFormatter(_file_formatter)

_logger.addHandler(_stdout)
_logger.addHandler(_stderr)
_logger.addHandler(_file)



def info(fmt, *args, **kwargs):
    _logger.info(fmt, *args, **kwargs)

def warning(fmt, *args, **kwargs):
    _logger.warning(fmt, *args, **kwargs)

def verbose(fmt, *args, **kwargs):
    _logger.log(VERBOSE, fmt, *args, **kwargs)

def debug(fmt, *args, **kwargs):
    _logger.debug(fmt, *args, **kwargs)

def error(fmt, *args, **kwargs):
    _logger.error(fmt, *args, **kwargs)

def stdout(line):
    line = line.replace("{", "{{")
    line = line.replace("}", "}}")
    _logger.log(STDOUT, line)

def stderr(line):
    line = line.replace("{", "{{")
    line = line.replace("}", "}}")
    _logger.log(STDERR, line)

def exception(exc=None):
    if exc:
        _logger.error(str(exc))
    backtrace = traceback.format_exc()
    for line in backtrace.splitlines():
        line = line.replace("{", "{{")
        line = line.replace("}", "}}")
        _logger.log(EXCEPTION, line)

def transfer(line, context):
    context = "[{}] ".format(context)
    outline1 = context + line[10:]
    outline2 = context + line
    if line.startswith("[  ERROR]"):
        error(outline1)
    elif line.startswith("[VERBOSE]"):
        verbose(outline1)
    elif line.startswith("[  DEBUG]"):
        debug(outline1)
    elif line.startswith("[   INFO]"):
        info(outline1)
    elif line.startswith("[ EXCEPT]"):
        outline1 = outline1.replace("{", "{{")
        outline1 = outline1.replace("}", "}}")
        _logger.log(EXCEPTION, outline1)
    elif line.startswith("[ STDERR]"):
        stderr(outline1)
    elif line.startswith("[ STDOUT]"):
        stdout(outline1)
    else:
        stdout(outline2)


class _Progress(object):
    def __init__(self, msg):
        verbose(msg)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        pass

    def update(self, *args, **kwargs):
        pass


def progress_log(desc, count, unit):
    return _Progress(desc)


def progress(desc, count, unit):
    if sys.stdout.isatty() and sys.stderr.isatty() and not is_verbose():
        p = tqdm.tqdm(total=count, unit=unit, unit_scale=True)
        p.set_description("[   INFO] " + desc)
        return p
    return progress_log(desc, count, unit)


def set_level(level):
    _stdout.setLevel(level)
    _stderr.setLevel(level)


def is_verbose():
    return _stdout.level <= VERBOSE


class _ThreadMapper(Filter):
    def __init__(self):
        self.thread_map = {}

    def map(self, fr, to):
        self.thread_map[fr] = to

    def unmap(self, fr):
        del self.thread_map[fr]

    def filter(self, record):
        record.thread = self.thread_map.get(record.thread, record.thread)
        return True

_thread_map = _ThreadMapper()


@contextmanager
def threadsink():
    threadid = threading.get_ident()
    stringbuf = StringIO()
    handler = logging.StreamHandler(stringbuf)
    handler.setLevel(DEBUG)
    handler.setFormatter(_file_formatter)
    handler.addFilter(_thread_map)
    handler.addFilter(Filter(lambda record: record.thread == threadid))
    _logger.addHandler(handler)
    yield stringbuf
    _logger.removeHandler(handler)


@contextmanager
def map_thread(thread_from, thread_to):
    tid = thread_from.ident
    _thread_map.map(tid, thread_to.ident)
    yield
    _thread_map.unmap(tid)


class _LogStream(object):
    def __init__(self):
        self.buf = ""

    def write(self, data):
        self.buf += data
        lines = self.buf.splitlines()
        if data[-1] != "\n":
            self.buf = lines[-1]
            lines = lines[:-1]
        else:
            self.buf = ""
        for line in lines:
            stdout(line)

    def flush(self):
        line = self.buf
        self.buf = ""
        if line:
            stdout(line)


@contextmanager
def stream():
    yield _LogStream()
