#!/usr/bin/python
import sys

from jolt import cli
from jolt import log


def main():
    try:
        cli.cli()
    except KeyboardInterrupt as e:
        log.warn("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        log.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
