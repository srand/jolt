#!/usr/bin/python
import os
import sys

from jolt import cli
from jolt import log
from jolt import config
from jolt import filesystem as fs


def start_pdb(sig, frame):
    import pdb
    pdb.Pdb().set_trace(frame)


def main():
    if os.name == "posix":
        import signal
        signal.signal(signal.SIGUSR1, start_pdb)

    try:
        cli.cli(obj=dict())
    except KeyboardInterrupt as e:
        log.warning("Interrupted by user")
        if cli.debug_enabled:
            import pdb
            extype, value, tb = sys.exc_info()
            pdb.post_mortem(tb)
        sys.exit(1)
    except Exception as e:
        log.exception(e)
        if cli.debug_enabled:
            import pdb
            extype, value, tb = sys.exc_info()
            pdb.post_mortem(tb)
        sys.exit(1)


if __name__ == "__main__":
    main()
