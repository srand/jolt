"""Pressure Stall Information (PSI) monitoring for the jobserver.

The jobserver stops handing out tokens while the system is under more
CPU, IO or memory pressure than configured. This mirrors BitBake's
BB_PRESSURE_MAX_{CPU,IO,MEMORY}: the cumulative 'some' stall time in
/proc/pressure/<resource> is sampled and converted into microseconds
of stall per second, which is compared against the configured limits.

This module is shared by the FIFO and CUSE jobservers. It must only
depend on the standard library, since the CUSE jobserver is deployed
as a standalone script.
"""

import os
import time


PSI_PATH = "/proc/pressure"
RESOURCES = ("cpu", "io", "memory")
MIN_LIMIT = 1
MAX_LIMIT = 1000000


def parse_limits(limits):
    """
    Validate pressure limits.

    Accepts a dict of resource name to limit. Unset limits (None or empty
    strings) are dropped. Raises ValueError for unknown resources and for
    limits outside the range 1..1000000.
    """
    result = {}
    for resource, value in (limits or {}).items():
        if value is None or value == "":
            continue
        if resource not in RESOURCES:
            raise ValueError("unknown pressure resource: {}".format(resource))
        try:
            value = float(value)
        except ValueError:
            raise ValueError("invalid {} pressure limit: {}".format(resource, value))
        if not MIN_LIMIT <= value <= MAX_LIMIT:
            raise ValueError("{} pressure limit must be between {} and {}, got {}".format(
                resource, MIN_LIMIT, MAX_LIMIT, value))
        result[resource] = value
    return result


class PressureMonitor:
    """ Tells whether system pressure exceeds the configured limits. """

    def __init__(self, limits, path=None):
        self.limits = parse_limits(limits)
        self.path = path or PSI_PATH
        self.rates = {}
        self.exceeded = False
        self._prev = None
        self._prev_time = None

    def _read_total(self, resource):
        # First line: "some avg10=0.00 avg60=0.00 avg300=0.00 total=12345"
        with open(os.path.join(self.path, resource)) as fp:
            fields = fp.readline().split()
        for field in fields:
            if field.startswith("total="):
                return float(field[len("total="):])
        raise ValueError("no total in {} pressure".format(resource))

    def _read(self):
        return {resource: self._read_total(resource) for resource in self.limits}

    def start(self):
        """
        Take the initial sample.

        Returns False if no limits are configured or if pressure
        information is unavailable, e.g. because the kernel lacks PSI
        support. Monitoring should then be disabled.
        """
        if not self.limits:
            return False
        try:
            self._prev = self._read()
        except (OSError, ValueError):
            return False
        self._prev_time = time.monotonic()
        return True

    def update(self):
        """
        Sample pressure since the previous call.

        Returns True if any limit is exceeded. Raises OSError or
        ValueError if pressure information can't be read.
        """
        curr = self._read()
        now = time.monotonic()
        tdiff = now - self._prev_time
        if tdiff <= 0:
            return self.exceeded
        self.rates = {
            resource: (curr[resource] - self._prev[resource]) / tdiff
            for resource in curr
        }
        self._prev, self._prev_time = curr, now
        self.exceeded = any(
            rate > self.limits[resource] for resource, rate in self.rates.items())
        return self.exceeded

    def describe(self):
        """ Current pressure versus limits, for logging. """
        return ", ".join(
            "{}: {}/{}".format(resource, round(self.rates.get(resource, 0.0), 1), int(limit))
            for resource, limit in self.limits.items())


# How often the pressure is sampled and the token limit adjusted, in seconds.
DEFAULT_INTERVAL = 0.25

# Seconds that the token limit takes to grow from idle to all tokens.
DEFAULT_RAMP_TIME = 30.0

# Seconds of sustained pressure between reductions of the token limit.
SHRINK_PERIOD = 1.0


class TokenRamp:
    """
    How many tokens may be handed out at once.

    The pressure monitor can only stop handing out tokens, not take them
    back, and the pressure of new jobs shows only after a second or two. A
    build could otherwise take all tokens before any pressure shows. The
    limit therefore grows gradually while there is demand and no pressure,
    reaching all tokens after the ramp time. Under pressure, it first holds
    at the tokens in use, and then falls to three quarters of them once a
    second for as long as the pressure lasts. Without demand, it falls back
    to the tokens in use, so that idle time doesn't build up a burst.
    """

    def __init__(self, tokens, ramp_time=DEFAULT_RAMP_TIME, interval=DEFAULT_INTERVAL, floor=0):
        self.tokens = tokens
        # Clients keep their implicit token, so builds progress without any
        self.floor = min(tokens, max(0, floor))
        # A ramp time of 0 disables the ramp: all tokens, except under pressure
        self.step = tokens * interval / ramp_time if ramp_time > 0 else tokens
        self.interval = interval
        self.limit = float(min(tokens, self.floor + self.step))
        self._pressured_for = 0.0

    @property
    def available(self):
        """ The number of tokens that may be handed out in total. """
        return int(self.limit)

    def update(self, in_use, demand, pressured):
        """
        Adjust the limit after an interval.

        in_use is the number of tokens handed out, demand whether clients
        wait for tokens, and pressured whether pressure exceeds a limit.
        Returns the new limit.
        """
        if pressured:
            if self._pressured_for == 0.0:
                # Start nothing new until the pressure eases
                self.limit = float(max(self.floor, min(self.limit, in_use)))
            elif self._pressured_for >= SHRINK_PERIOD:
                self.limit = float(max(self.floor, (in_use * 3) // 4))
                self._pressured_for = 0.0
            self._pressured_for += self.interval
        else:
            self._pressured_for = 0.0
            if demand or in_use >= self.available:
                self.limit = max(self.limit, float(in_use)) + self.step
            else:
                self.limit = min(self.limit, in_use + self.step)
            self.limit = max(float(self.floor), min(float(self.tokens), self.limit))
        return self.available
