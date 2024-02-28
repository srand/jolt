#!/usr/bin/python
import os
import sys

from jolt import cli
from jolt import error
from jolt import log


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


def main():
    if os.name == "posix":
        import signal
        signal.signal(signal.SIGUSR1, start_pdb)
        signal.signal(signal.SIGUSR2, dump_threads)

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
