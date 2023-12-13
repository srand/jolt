from __future__ import print_function
import glob
import os
import re
import sys
import time
import tqdm
if os.name == "nt":
    # FIXME: Workaround to make tqdm behave correctly on Windows
    import colorama
    colorama.deinit()  # Undo the work of tqdm
    os.system("")      # Hack to enable vt100
import traceback
from datetime import datetime
import threading
import logging
import logging.handlers
from contextlib import contextmanager
try:
    from StringIO import StringIO
except Exception:
    from io import StringIO

from jolt import config
from jolt.error import JoltError
from jolt import filesystem as fs
from jolt import colors
from jolt import common_pb2 as common_pb


current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")
logpath = config.get_logpath()
logfile = fs.path.join(logpath, f"{current_time}.log")
logcount = config.getint("jolt", "logcount", os.environ.get("JOLT_LOGCOUNT", 100))
logfiles = list(sorted(glob.glob(os.path.join(logpath, "*T*.log"))))

dirpath = fs.path.dirname(logfile)
if not fs.path.exists(dirpath):
    fs.makedirs(dirpath)

################################################################################

ERROR = common_pb.LogLevel.ERROR
WARNING = common_pb.LogLevel.WARNING
INFO = common_pb.LogLevel.INFO
VERBOSE = common_pb.LogLevel.VERBOSE
DEBUG = common_pb.LogLevel.DEBUG
EXCEPTION = common_pb.LogLevel.EXCEPTION
STDOUT = common_pb.LogLevel.STDOUT
STDERR = common_pb.LogLevel.STDERR
SILENCE = STDERR + 1

logging.addLevelName(VERBOSE, "VERBOSE")
logging.addLevelName(STDOUT, "STDOUT")
logging.addLevelName(STDERR, "STDERR")
logging.addLevelName(EXCEPTION, "EXCEPT")
logging.addLevelName(WARNING, "WARNING")
logging.addLevelName(INFO, "INFO")
logging.addLevelName(ERROR, "ERROR")
logging.addLevelName(DEBUG, "DEBUG")

logging.raiseExceptions = False


class Formatter(logging.Formatter):
    def __init__(self, fmt, *args, **kwargs):
        super(Formatter, self).__init__(*args, **kwargs)
        self.fmt = fmt

    def format(self, record):
        try:
            record.message = record.msg.format(*record.args)
        except Exception:
            record.message = record.msg
        record.asctime = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")
        return self.fmt.format(
            levelname=record.levelname,
            message=record.message,
            asctime=record.asctime
        )


class ConsoleFormatter(logging.Formatter):
    def __init__(self, fmt_prefix, fmt_noprefix, *args, **kwargs):
        super(ConsoleFormatter, self).__init__(*args, **kwargs)
        self.fmt_prefix = fmt_prefix
        self.fmt_noprefix = fmt_noprefix
        self.always_prefix = False

    def enable_prefixes(self):
        self.always_prefix = True

    def enable_gdb(self):
        self.always_prefix = True
        self.fmt_prefix = "~\"" + self.fmt_prefix + "\\n\""

    def format(self, record):
        try:
            msg = record.msg.format(*record.args)
        except Exception:
            msg = record.msg
        if sys.stdout.isatty() and sys.stderr.isatty():
            if record.levelno >= ERROR:
                msg = colors.red(msg)
            elif record.levelno >= WARNING:
                msg = colors.yellow(msg)
        record.message = msg
        record.asctime = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")
        record.prefix = True if record.__dict__.get("prefix", False) else False

        if not record.prefix and \
           not self.always_prefix and \
           record.levelno in [STDOUT, STDERR]:
            fmt = self.fmt_noprefix
        else:
            fmt = self.fmt_prefix

        return fmt.format(
            levelname=record.levelname,
            message=record.message,
            asctime=record.asctime
        )


class Filter(logging.Filter):
    def __init__(self, filterfn):
        self.filterfn = filterfn

    def filter(self, record):
        return self.filterfn(record)


class TqdmStream(object):
    def __init__(self, stream):
        self.stream = stream

    def write(self, msg):
        with tqdm.tqdm.external_write_mode(file=self.stream, nolock=False):
            self.stream.write(msg)

    def flush(self):
        getattr(self.stream, 'flush', lambda: None)()


# silence root logger
_root = logging.getLogger()
_root.setLevel(logging.CRITICAL)

# create jolt logger
_logger = logging.getLogger('jolt')
_logger.setLevel(DEBUG)

_console_formatter = ConsoleFormatter('[{levelname:>7}] {message}', '{message}')

if sys.stdout.isatty() and sys.stderr.isatty():
    _stdout = logging.StreamHandler(TqdmStream(sys.stdout))
else:
    _stdout = logging.StreamHandler(sys.stdout)
_stdout.setFormatter(_console_formatter)
_stdout.addFilter(Filter(lambda r: r.levelno < ERROR))

if sys.stdout.isatty() and sys.stderr.isatty():
    _stderr = logging.StreamHandler(TqdmStream(sys.stdout))
else:
    _stderr = logging.StreamHandler(sys.stderr)
_stderr.setFormatter(_console_formatter)
_stderr.addFilter(Filter(lambda r: r.levelno >= ERROR))
_stderr.addFilter(Filter(lambda r: r.levelno != EXCEPTION))

_logger.addHandler(_stdout)
_logger.addHandler(_stderr)

_file_formatter = Formatter('{asctime} [{levelname:>7}] {message}')


def start_file_log():
    global logfiles

    if len(logfiles) >= logcount:
        outdated = logfiles[:len(logfiles) - logcount + 1]
        logfiles = logfiles[-logcount + 1:]
        for file in outdated:
            os.unlink(file)

    _file = logging.FileHandler(logfile)
    _file.setLevel(DEBUG)
    _file.setFormatter(_file_formatter)
    _logger.addHandler(_file)


def log(level, message, created=None, context=None, prefix=False):
    created = created or time.time()
    message = f"[{context}] {message}" if context else message
    record = logging.LogRecord(
        name="log",
        level=level,
        pathname=__file__,
        lineno=0,
        msg=message,
        args={},
        exc_info=None,
    )
    record.created = created
    record.prefix = prefix
    _logger.handle(record)


def info(fmt, *args, **kwargs):
    _logger.log(INFO, fmt, *args, **kwargs)


def warning(fmt, *args, **kwargs):
    _logger.log(WARNING, fmt, *args, **kwargs)


def verbose(fmt, *args, **kwargs):
    _logger.log(VERBOSE, fmt, *args, **kwargs)


def debug(fmt, *args, **kwargs):
    _logger.log(DEBUG, fmt, *args, **kwargs)


def error(fmt, *args, **kwargs):
    _logger.log(ERROR, fmt, *args, **kwargs)


def stdout(line, **kwargs):
    line = line.replace("{", "{{")
    line = line.replace("}", "}}")
    _logger.log(STDOUT, line, extra=kwargs)


def stderr(line, **kwargs):
    line = line.replace("{", "{{")
    line = line.replace("}", "}}")
    _logger.log(STDERR, line, extra=kwargs)


def format_exception_msg(exc):
    te = traceback.TracebackException.from_exception(exc)

    if isinstance(exc, JoltError):
        return str(exc)

    elif isinstance(exc, SyntaxError):
        filename = fs.path.relpath(
            te.filename,
            fs.path.commonprefix([os.getcwd(), te.filename]))
        return "SyntaxError: {} ({}, line {})".format(
            te.text.strip(),
            filename,
            te.lineno)

    else:
        filename = fs.path.relpath(
            te.stack[-1].filename,
            fs.path.commonprefix([os.getcwd(), te.stack[-1].filename]))
        return "{}: {} ({}, line {}, in {})".format(
            type(exc).__name__,
            str(exc) or te.stack[-1].line,
            filename,
            te.stack[-1].lineno,
            te.stack[-1].name)


def exception(exc=None):
    if exc:
        _logger.error(format_exception_msg(exc))
        backtrace = traceback.format_exc().splitlines()
    else:
        backtrace = traceback.format_exc().splitlines()

    for line in backtrace:
        line = line.replace("{", "{{")
        line = line.replace("}", "}}")
        line = line.strip()
        _logger.log(EXCEPTION, line)


def transfer(line, context):
    context = "[{}] ".format(context)
    outline1 = context + line[10:]
    outline2 = context + line
    if line.startswith("[  ERROR]"):
        error(outline1)
    elif line.startswith("[WARNING]"):
        warning(outline1)
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
        stderr(outline1, prefix=True)
    elif line.startswith("[ STDOUT]"):
        stdout(outline1, prefix=True)
    else:
        stdout(outline2, prefix=True)


def decompose(line):
    match = re.match(r"(?P<timestamp>[0-9]{4}-[0-9]{1,2}-[0-9]{1,2} [0-9]{1,2}:[0-9]{1,2}:[0-9]{1,2}.[0-9]{6}) \[(?P<loglevel>.*?)\]( \[(?P<context>.*?)\])? (?P<message>.*)", line)
    if not match:
        return line
    match = match.groupdict()
    return match["timestamp"], match["loglevel"].strip(), match.get("context"), match["message"]


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


def progress(desc, count, unit, estimates=True, debug=False):
    bar_format = '{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]' \
                 if not estimates else None
    if not debug and is_interactive() and not is_verbose():
        p = tqdm.tqdm(total=count, unit=unit, unit_scale=True, bar_format=bar_format, dynamic_ncols=True)
        p.set_description("[   INFO] " + desc)
        return p
    return progress_log(desc, count, unit)


_level = INFO


def set_level(level):
    global _level
    _level = level
    _stdout.setLevel(level)
    _stderr.setLevel(level)


def get_level():
    global _level
    return _level


def set_worker():
    _console_formatter.enable_prefixes()


def enable_gdb():
    set_interactive(False)
    _console_formatter.enable_gdb()


def is_verbose():
    return _stdout.level <= VERBOSE


_interactive = True


def is_interactive():
    global _interactive
    return _interactive and sys.stdout.isatty() and sys.stderr.isatty()


def set_interactive(value):
    global _interactive
    _interactive = value


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
def threadsink(level=DEBUG):
    threadid = threading.get_ident()
    stringbuf = StringIO()
    handler = logging.StreamHandler(stringbuf)
    handler.setLevel(level)
    handler.setFormatter(_file_formatter)
    handler.addFilter(_thread_map)
    handler.addFilter(Filter(lambda record: record.thread == threadid))
    _logger.addHandler(handler)
    try:
        yield stringbuf
    finally:
        _logger.removeHandler(handler)


@contextmanager
def handler(h):
    _logger.addHandler(h)
    try:
        yield
    finally:
        _logger.removeHandler(h)


@contextmanager
def map_thread(thread_from, thread_to):
    tid = thread_from.ident
    _thread_map.map(tid, thread_to.ident)
    try:
        yield
    finally:
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


set_level(INFO)
