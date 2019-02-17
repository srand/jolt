#!/usr/bin/python
import sys
import signal

from jolt import cli
from jolt import log


def start_pdb(sig, frame):
    import pdb
    pdb.Pdb().set_trace(frame)


def main():
    signal.signal(signal.SIGUSR1, start_pdb)

    try:
        cli.cli(obj={})
    except KeyboardInterrupt as e:
        log.warn("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        log.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
