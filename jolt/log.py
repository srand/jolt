from __future__ import print_function
import atexit
import glob
import os
import re
import sys
import time
if os.name == "posix":
    import termios
if os.name == "nt":
    os.system("")      # Hack to enable vt100
import traceback
from datetime import datetime
import threading
import logging
import logging.handlers
from contextlib import contextmanager
from rich.console import Console
from rich.constrain import Constrain
from rich.control import Control, ControlType
from rich.live import Live
from rich.live_render import LiveRender
from rich.measure import Measurement
from rich.progress import (
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.style import Style
from rich.table import Column
from rich.text import Text
try:
    from StringIO import StringIO
except Exception:
    from io import StringIO

from jolt import config
from jolt.error import JoltError
from jolt import filesystem as fs
from jolt import colors
from jolt import common_pb2 as common_pb
from jolt import utils


current_time = datetime.now().strftime("%Y-%m-%dT%H%M%S.%f")
logpath = config.get_logpath()
logfile = fs.path.join(logpath, f"{current_time}.log")
logcount = config.getint("jolt", "logcount", os.environ.get("JOLT_LOGCOUNT", 100))
logfiles = list(sorted(glob.glob(os.path.join(logpath, "*T*.log"))))

dirpath = fs.path.dirname(logfile)
if not fs.path.exists(dirpath):
    fs.makedirs(dirpath)

################################################################################

ERROR = common_pb.LogLevel.ERROR + 1
WARNING = common_pb.LogLevel.WARNING + 1
INFO = common_pb.LogLevel.INFO + 1
VERBOSE = common_pb.LogLevel.VERBOSE + 1
DEBUG = common_pb.LogLevel.DEBUG + 1
EXCEPTION = common_pb.LogLevel.EXCEPTION + 1
STDOUT = common_pb.LogLevel.STDOUT + 1
STDERR = common_pb.LogLevel.STDERR + 1
SILENCE = STDERR + 2

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


class ConsoleStream(object):
    """
    Terminal stream that prints lines above progress bars.

    While progress bars are shown, complete lines are printed through
    the rich console, which keeps the bars below the output. Otherwise,
    output is written to the stream directly.
    """

    def __init__(self, stream):
        self.stream = stream
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, msg):
        with self._lock:
            if _ProgressDisplay.live is None and not self._buffer:
                self.stream.write(msg)
                return
            lines = (self._buffer + msg).split("\n")
            self._buffer = lines.pop()
        for line in lines:
            _console.print(Text.from_ansi(line), soft_wrap=True)

    def flush(self):
        getattr(self.stream, 'flush', lambda: None)()


class ThreadPrefix(logging.LoggerAdapter):
    thread_prefix = {}

    def process(self, msg, kwargs):
        tid = threading.current_thread()
        if tid in self.thread_prefix:
            msg = f"[{self.thread_prefix[tid]}] {msg}"
        return msg, kwargs

    def set_thread_prefix(self, prefix):
        tid = threading.current_thread()
        self.thread_prefix[tid] = prefix

    def clear_thread_prefix(self):
        tid = threading.current_thread()
        if tid in self.thread_prefix:
            del self.thread_prefix[tid]


# silence root logger
_root = logging.getLogger()
_root.setLevel(logging.CRITICAL)

# create jolt logger and protect it's methods against interrupts
_logger = logging.getLogger('jolt')
_logger.setLevel(EXCEPTION)
_logger.handle = utils.delay_interrupt(_logger.handle)
_logger.log = utils.delay_interrupt(_logger.log)
_logger.addHandler = utils.delay_interrupt(_logger.addHandler)
_logger.removeHandler = utils.delay_interrupt(_logger.removeHandler)


_console_formatter = ConsoleFormatter('[{levelname:>7}] {message}', '{message}')

_console = Console(file=sys.stdout, highlight=False, emoji=False, markup=False, soft_wrap=True)

if sys.stdout.isatty() and sys.stderr.isatty():
    _stdout = logging.StreamHandler(ConsoleStream(sys.stdout))
else:
    _stdout = logging.StreamHandler(sys.stdout)
_stdout.setFormatter(_console_formatter)
_stdout.addFilter(Filter(lambda r: r.levelno < ERROR))
_stdout.addFilter(Filter(lambda r: r.levelno != EXCEPTION))

if sys.stdout.isatty() and sys.stderr.isatty():
    _stderr = logging.StreamHandler(ConsoleStream(sys.stdout))
else:
    _stderr = logging.StreamHandler(sys.stderr)
_stderr.setFormatter(_console_formatter)
_stderr.addFilter(Filter(lambda r: r.levelno >= ERROR or r.levelno == EXCEPTION))

_logger.addHandler(_stdout)
_logger.addHandler(_stderr)
_logger_frontend = ThreadPrefix(_logger, {})

_file_formatter = Formatter('{asctime} [{levelname:>7}] {message}')


def start_file_log():
    global logfiles

    if len(logfiles) >= logcount:
        outdated = logfiles[:len(logfiles) - logcount + 1]
        logfiles = logfiles[-logcount + 1:]
        for file in outdated:
            os.unlink(file)

    _file = logging.FileHandler(logfile)
    _file.setLevel(EXCEPTION)
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
    _logger_frontend.log(INFO, fmt, *args, **kwargs)


def warning(fmt, *args, **kwargs):
    _logger_frontend.log(WARNING, fmt, *args, **kwargs)


def verbose(fmt, *args, **kwargs):
    _logger_frontend.log(VERBOSE, fmt, *args, **kwargs)


def debug(fmt, *args, **kwargs):
    _logger_frontend.log(DEBUG, fmt, *args, **kwargs)


def error(fmt, *args, **kwargs):
    _logger_frontend.log(ERROR, fmt, *args, **kwargs)


def stdout(line, **kwargs):
    line = line.replace("{", "{{")
    line = line.replace("}", "}}")
    _logger_frontend.log(STDOUT, line, extra=kwargs)


def stderr(line, **kwargs):
    line = line.replace("{", "{{")
    line = line.replace("}", "}}")
    _logger_frontend.log(STDERR, line, extra=kwargs)


def format_exception_msg(exc):
    te = traceback.TracebackException.from_exception(exc)

    if isinstance(exc, JoltError):
        return str(exc)

    elif isinstance(exc, SyntaxError):
        filename = fs.as_relpath(te.filename, os.getcwd())
        return "SyntaxError: {} ({}, line {})".format(
            te.text.strip(),
            filename,
            te.lineno)

    else:
        filename = fs.as_relpath(te.stack[-1].filename, os.getcwd())
        return "{}: {} ({}, line {}, in {})".format(
            type(exc).__name__,
            str(exc) or te.stack[-1].line,
            filename,
            te.stack[-1].lineno,
            te.stack[-1].name)


def exception(exc=None, error=True):
    if exc:
        if error:
            _logger_frontend.log(ERROR, format_exception_msg(exc))

        tb = traceback.format_exception(type(exc), value=exc, tb=exc.__traceback__)
        installdir = fs.path.dirname(__file__)
        if any(map(lambda frame: installdir not in frame, tb[1:-1])):
            while len(tb) > 2 and installdir in tb[1]:
                del tb[1]
        backtrace = "".join(tb).splitlines()
    else:
        backtrace = traceback.format_exc().splitlines()

    for line in backtrace:
        line = line.replace("{", "{{")
        line = line.replace("}", "}}")
        line = line.strip()
        _logger_frontend.log(EXCEPTION, line)


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
        _logger_frontend.log(EXCEPTION, outline1)
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

    def refresh(self, *args, **kwargs):
        pass

    def reset(self, *args, **kwargs):
        pass

    def set_description(self, *args, **kwargs):
        pass


def progress_log(desc, count, unit):
    return _Progress(desc)


class _BlockBar(object):
    """ Progress bar drawn with block characters across the available width. """

    _partial = " ▏▎▍▌▋▊▉"

    def __init__(self, completed, total, finished):
        self.completed = completed
        self.total = total
        self.finished = finished

    def __rich_console__(self, console, options):
        width = options.max_width
        ratio = min(1.0, self.completed / self.total) if self.total else 0.0
        full, eighths = divmod(int(ratio * width * 8), 8)
        bar = "█" * full
        if eighths and full < width:
            bar += self._partial[eighths]
        color = console.get_style("bar.finished" if self.finished else "bar.complete").color
        yield Text(bar.ljust(width), style=Style(color=color, bgcolor="grey23"), end="")

    def __rich_measure__(self, console, options):
        return Measurement(1, options.max_width)


class _BlockBarColumn(ProgressColumn):
    """ Column with a block progress bar that fills the remaining width. """

    def __init__(self):
        super().__init__(table_column=Column(ratio=1, no_wrap=True))

    def render(self, task):
        if task.total is None:
            return Text("")
        return _BlockBar(task.completed, task.total, task.finished)


class _DescriptionColumn(TextColumn):
    """
    Description column with a fixed width.

    The width, including the log level, shrinks in narrow terminals to
    leave room for the bar and the other columns.
    """

    max_width = 48
    min_width = 24
    reserved_width = 52

    def __init__(self):
        super().__init__("[   INFO] {task.description}", markup=False)

    def get_table_column(self):
        width = max(self.min_width, min(self.max_width, _console.width - self.reserved_width))
        return Column(width=width, no_wrap=True, overflow="ellipsis")


class _DetailsColumn(ProgressColumn):
    """ Counters of a progress bar, in a format depending on the unit. """

    def __init__(self):
        super().__init__(table_column=Column(width=24, justify="right", no_wrap=True, overflow="ellipsis"))
        self._download = DownloadColumn()
        self._speed = TransferSpeedColumn()
        self._count = MofNCompleteColumn()

    def render(self, task):
        unit = task.fields.get("unit", "")
        if task.total is None:
            return Text("{:.0f} {}".format(task.completed, unit))
        if unit == "B":
            if (task.finished_speed or task.speed) is None:
                return self._download.render(task)
            return Text.assemble(self._download.render(task), " ", self._speed.render(task))
        return Text.assemble(self._count.render(task), " ", unit)


class _RemainingColumn(ProgressColumn):
    """ Estimated time remaining, for bars with estimates only. """

    def __init__(self):
        super().__init__(table_column=Column(width=7, no_wrap=True))
        self._remaining = TimeRemainingColumn()

    def render(self, task):
        if task.total is None or not task.fields.get("estimates"):
            return Text("")
        return self._remaining.render(task)


class _ReflowLiveRender(LiveRender):
    """
    Live render that handles terminals reflowing lines when resized.

    When a terminal is made narrower, many terminals wrap the lines that
    were already drawn onto several rows. The cursor must then be moved
    up past all of those rows to erase the previous render.
    """

    def _rows(self):
        width, height = self._shape
        new_width = max(1, _console.width)
        if width > new_width:
            return height * -(-width // new_width)
        return height

    def position_cursor(self):
        if self._shape is None:
            return Control()
        return Control(
            ControlType.CARRIAGE_RETURN,
            (ControlType.ERASE_IN_LINE, 2),
            *(((ControlType.CURSOR_UP, 1), (ControlType.ERASE_IN_LINE, 2)) * (self._rows() - 1)))

    def restore_cursor(self):
        if self._shape is None:
            return Control()
        return Control(
            ControlType.CARRIAGE_RETURN,
            *((ControlType.CURSOR_UP, 1), (ControlType.ERASE_IN_LINE, 2)) * self._rows())


class _TerminalEcho(object):
    """
    Disables echo of typed keys while progress bars are shown.

    Echoed keys, such as enter, move the cursor and break the redraw of
    the bars. Signal keys like Ctrl-C keep working since only echo is
    disabled, and typed input is still passed on to whoever reads it.
    """

    fd = None
    attrs = None

    @staticmethod
    def disable():
        if os.name != "posix" or _TerminalEcho.attrs is not None:
            return
        try:
            fd = sys.stdin.fileno()
            # Changing terminal attributes stops background processes
            if not os.isatty(fd) or os.tcgetpgrp(fd) != os.getpgrp():
                return
            attrs = termios.tcgetattr(fd)
            noecho = list(attrs)
            noecho[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, noecho)
            _TerminalEcho.fd, _TerminalEcho.attrs = fd, attrs
        except (AttributeError, ValueError, OSError, termios.error):
            pass

    @staticmethod
    def restore():
        if _TerminalEcho.attrs is None:
            return
        try:
            termios.tcsetattr(_TerminalEcho.fd, termios.TCSANOW, _TerminalEcho.attrs)
        except (ValueError, OSError, termios.error):
            pass
        _TerminalEcho.fd, _TerminalEcho.attrs = None, None


atexit.register(_TerminalEcho.restore)


class _ProgressDisplay(object):
    """
    Live terminal region that shows all open progress bars.

    All bars are rows of one table with fixed width columns, except for
    the bar itself, so that bars shown at the same time line up. The
    region is redrawn a few times per second and log output is printed
    above it.
    """

    lock = threading.RLock()
    live = None
    details = _DetailsColumn()
    elapsed = TimeElapsedColumn(table_column=Column(width=7, no_wrap=True))
    progress = Progress(
        _DescriptionColumn(),
        _BlockBarColumn(),
        details,
        elapsed,
        _RemainingColumn(),
        console=_console,
        auto_refresh=False,
        expand=True)

    def __rich_console__(self, console, options):
        # Called by the refresh thread of rich while it holds its own
        # lock, don't take the display lock here.
        # Leave the last column empty. Terminals treat lines that fill the
        # whole width differently when reflowing them on resize.
        table = _ProgressDisplay.progress.make_tasks_table(_ProgressDisplay.progress.tasks)
        yield Constrain(table, width=max(1, options.max_width - 1))

    @staticmethod
    def add(desc, total, unit, estimates):
        with _ProgressDisplay.lock:
            task = _ProgressDisplay.progress.add_task(desc, total=total, unit=unit, estimates=estimates)
            if _ProgressDisplay.live is None:
                _ProgressDisplay.live = Live(
                    _ProgressDisplay(),
                    console=_console,
                    refresh_per_second=4,
                    transient=True,
                    redirect_stdout=False,
                    redirect_stderr=False)
                _ProgressDisplay.live._live_render = _ReflowLiveRender(
                    _ProgressDisplay.live.get_renderable(),
                    vertical_overflow=_ProgressDisplay.live.vertical_overflow)
                _TerminalEcho.disable()
                _ProgressDisplay.live.start()
            return task

    @staticmethod
    def remove(task_id):
        with _ProgressDisplay.lock:
            progress = _ProgressDisplay.progress
            tasks = [task for task in progress.tasks if task.id == task_id]
            if not tasks:
                return
            task = tasks[0]
            details = _ProgressDisplay.details.render(task).plain.strip()
            elapsed = _ProgressDisplay.elapsed.render(task).plain

            # The live region is erased when stopped, stop it before the
            # last bar is removed so that no empty line is left behind.
            if len(progress.tasks) == 1:
                try:
                    _ProgressDisplay.live.stop()
                finally:
                    _ProgressDisplay.live = None
                    _TerminalEcho.restore()
            progress.remove_task(task_id)

        # Replace the bar with a log line
        info("{} ({}, {})", task.description, details, elapsed)


class _RichProgress(object):
    def __init__(self, desc, count, unit, estimates):
        self._desc = desc
        self._total = count or None
        self._unit = unit.strip()
        self._estimates = estimates
        self._task = None

    def __enter__(self):
        self._task = _ProgressDisplay.add(self._desc, self._total, self._unit, self._estimates)
        return self

    def __exit__(self, type, value, tb):
        _ProgressDisplay.remove(self._task)
        return False

    def update(self, n=1):
        if self._task is not None:
            _ProgressDisplay.progress.advance(self._task, n)

    def refresh(self, *args, **kwargs):
        pass

    def reset(self, total=None):
        if self._task is not None:
            _ProgressDisplay.progress.reset(self._task, total=total)

    def set_description(self, desc=None, refresh=True):
        self._desc = desc
        if self._task is not None:
            _ProgressDisplay.progress.update(self._task, description=desc)


def progress(desc, count, unit, estimates=True, debug=False):
    if not debug and is_interactive() and not is_verbose() and not is_silenced():
        return _RichProgress(desc, count, unit, estimates)
    return progress_log(desc, count, unit)


_level = INFO


def level_to_pb(level):
    """ Convert a log level to a protobuf enum value. """
    return level - 1


def pb_to_level(level):
    """ Convert a protobuf enum value to a log level. """
    return level + 1


def set_level(level):
    """ Set the log level for terminal output. """

    if level not in [
        DEBUG,
        ERROR,
        EXCEPTION,
        INFO,
        SILENCE,
        STDERR,
        STDOUT,
        VERBOSE,
        WARNING,
    ]:
        raise ValueError("invalid log level")

    global _level
    _level = level
    _stdout.setLevel(level)
    _stderr.setLevel(level)


def set_level_pb(level):
    """ Set the log level from a protobuf enum value. """
    set_level(pb_to_level(level))


def get_level():
    global _level
    return _level


def get_level_pb():
    """ Get the log level as a protobuf enum value. """
    return level_to_pb(_level)


def set_worker():
    _console_formatter.enable_prefixes()


def enable_gdb():
    set_interactive(False)
    _console_formatter.enable_gdb()


def is_verbose():
    return _stdout.level <= VERBOSE


def is_silenced():
    """ Returns True if informational messages aren't printed to the terminal. """
    return _stdout.level > INFO


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


@contextmanager
def thread_prefix(prefix):
    try:
        _logger_frontend.set_thread_prefix(prefix)
        yield
    finally:
        _logger_frontend.clear_thread_prefix()


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


set_level(STDOUT)
