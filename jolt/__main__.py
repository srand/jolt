#!/usr/bin/python
import os
import sys

from setproctitle import setproctitle

from jolt import cli
from jolt import error
from jolt import log


def _build_process_title(name):
    return " ".join([name] + sys.argv[1:])


def start_pdb(sig, frame):
    import pdb
    pdb.Pdb().set_trace(frame)


def dump_threads(sig, frame):
    import traceback
    print("\n===============================================================================")
    for threadId, stack in sys._current_frames().items():
        print("\n--- ThreadID:", threadId)
        for filename, lineno, name, line in traceback.extract_stack(stack):
            print('File: "{}", line {}, in {}'.format(filename, lineno, name))
            if line:
                print("  " + line.strip())
    print("\n===============================================================================\n")


def terminate(sig, frame):
    import signal
    if os.name != "posix":
        signal.default_int_handler(sig, frame)

    # Interrupt Jolt and the commands in its process group, as the terminal does on Ctrl-C
    import psutil
    # Scripts that start Jolt in the background make it and its commands ignore SIGINT
    ignored = signal.getsignal(signal.SIGINT) is signal.SIG_IGN
    pgrp = os.getpgrp()
    try:
        children = psutil.Process().children(recursive=True)
    except psutil.Error:
        children = []
    for child in children:
        try:
            if os.getpgid(child.pid) == pgrp:
                child.send_signal(signal.SIGTERM if ignored else signal.SIGINT)
        except (OSError, psutil.Error):
            pass
    if ignored:
        signal.default_int_handler(sig, frame)
    os.kill(os.getpid(), signal.SIGINT)


def main():
    setproctitle(_build_process_title("jolt"))

    import signal
    if os.name == "posix":
        signal.signal(signal.SIGUSR1, start_pdb)
        signal.signal(signal.SIGUSR2, dump_threads)
    signal.signal(signal.SIGTERM, terminate)
    if hasattr(signal, "SIGBREAK"):
        # Ctrl-Break, used on Windows to stop console programs gracefully
        signal.signal(signal.SIGBREAK, terminate)

    try:
        cli.cli(obj=dict())
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        if cli.debug_enabled:
            import pdb
            extype, value, tb = sys.exc_info()
            pdb.post_mortem(tb)
        sys.exit(1)
    except error.LoggedJoltError as e:
        log.error(log.format_exception_msg(e.exc))
        if cli.debug_enabled:
            import pdb
            extype, value, tb = sys.exc_info()
            pdb.post_mortem(tb)
        sys.exit(1)
    except Exception as e:
        log.exception(e, error=True)
        if cli.debug_enabled:
            import pdb
            extype, value, tb = sys.exc_info()
            pdb.post_mortem(tb)
        sys.exit(1)


if __name__ == "__main__":
    main()
