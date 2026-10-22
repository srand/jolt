# Command timeout hangs while joining a stderr reader blocked on logging

## Status

Confirmed in a live worker running Jolt **0.10.61** with Python **3.12.8**.
Still reproducible in upstream **0.10.65**, commit
`5ee26da378da006be1acb5e9235589d2667c1a89`, using Python **3.14.4**.

The deployed and upstream copies of `jolt/tools.py`, `jolt/utils.py`, and
`jolt/log.py` were byte-for-byte identical when compared on 2026-10-22.

## Incident

- Pod: `production/jolt-worker-default-v2-698d9bc6c-62nn2`.
- Node: `px2csw16.scs.domain`.
- Task: `px2/test/openprotocol/test_open_protocol_commands_disabled`.
- Task identity prefix: `0a068fe4`.
- Executor PID at inspection: `3465518`.
- Task started on **2026-10-21 at 15:28:48 CEST**.
- The pytest command had an explicit **900-second timeout**, configured in
  `px2system/Jolt/test.build:939-945`.
- Last worker output was at **15:43:48 CEST**, at the command timeout deadline.
- Almost 23 hours later, pytest was no longer running, but the executor and
  the virtual controller, FlexNet license server, and Tool Simulator containers
  were still running.

The pod was Ready, with zero restarts, no reported events, and low CPU/memory
usage. This was not a Kubernetes scheduling or resource-exhaustion failure.

## Confirmed live state

A nonblocking `py-spy` stack dump showed:

```text
MainThread
  threading.Thread.join()
  jolt/tools.py:380 in _run: stderr.join()
  px2system/Jolt/test.build:939 in run: tools.run(...)

Thread-37 (stderr Reader)
  logging/__init__.py:241 in _acquireLock
  logging/__init__.py:1800 in isEnabledFor
  jolt/log.py:263 in stderr
  jolt/tools.py:111 in Reader.run: self.output(line)
```

The executor's `_run` frame contained `timedout=True` and
`kwargs={"timeout": 900, "shell": False}`. This confirms that the command
timeout was handled before execution became stuck joining the stderr reader.

The reader was trying to log this line:

```text
<2026-10-21T13:28:50.888Z> INFO [pytest_runtest_setup] -
```

It was blocked on Python logging's module-level lock, not on a pipe read.

## Failure mechanism

1. `_wait_for_process()` catches `subprocess.TimeoutExpired` or
   `JoltTimeoutError`, stops the command, and returns `True`
   (`jolt/tools.py:200-212`).
2. `_run()` then calls `stdout.join()` and `stderr.join()` **without a timeout**
   (`jolt/tools.py:378-380`).
3. A reader that cannot complete its logging callback prevents either join
   from returning, even though the command has already stopped.
4. `_raise_process_error()` is never reached, so the caller never receives
   `JoltTimeoutError`. Task error handling and resource release cannot proceed.

`READER_JOIN_TIMEOUT` and `_cleanup_interrupted_process()` already provide
bounded joins for **KeyboardInterrupt**. The command-timeout path does not use
that bounded cleanup. `_PopenFile.finalize()` also contains an unbounded stderr
join and stdout read, although that path was not involved in this incident.

### What remains unknown

The live stack confirms the blocked logging lock, but does **not** establish
who owns it or why it remained held. It also does not establish why pytest
failed to progress during its initial setup; the pytest process had already
been terminated when inspected.

`utils.timeout()` uses `PyThreadState_SetAsyncExc`, so asynchronous exception
delivery around lock acquisition is worth investigating, but it is not a
confirmed cause of the retained logging lock in this incident.

## Local reproduction

Run from the repository root with Jolt's Python dependencies installed. This
reproduces the failure when logging cannot make progress; it does not reproduce
the original cause of the retained logging lock. It uses a one-second timeout,
temporarily holds the logging lock, and releases it in `finally`.

```python
import logging
import os
import sys
import threading
from unittest.mock import patch

from jolt import tools
from jolt.error import JoltTimeoutError

result = []


def invoke():
    try:
        tools._run(
            [sys.executable, "-c",
             "import sys,time; "
             "print('stderr repro',file=sys.stderr,flush=True); "
             "time.sleep(30)"],
            None,
            os.environ.copy(),
            timeout=1,
            shell=False,
        )
    except BaseException as exc:
        result.append(exc)


worker = threading.Thread(target=invoke, daemon=True)
with patch.object(tools.log, "debug"):
    logging._lock.acquire()
    try:
        # Force the stderr logging callback to acquire the logging lock.
        tools.log._logger_frontend.logger._cache.pop(tools.log.STDERR, None)
        worker.start()
        worker.join(3)
        assert worker.is_alive()

        frame = sys._current_frames()[worker.ident]
        while frame and not (
            frame.f_code.co_name == "_run"
            and frame.f_code.co_filename.endswith("jolt/tools.py")
        ):
            frame = frame.f_back
        assert frame is not None
        assert frame.f_locals["timedout"] is True
        print("Command timed out, but _run is still blocked joining stderr")
    finally:
        logging._lock.release()

    worker.join(5)
    assert not worker.is_alive()
    assert len(result) == 1 and isinstance(result[0], JoltTimeoutError)
    print("Releasing the logging lock allows JoltTimeoutError to propagate")
```

Observed on upstream 0.10.65: after three seconds the worker was still blocked
at `jolt/tools.py:380`, with `timedout=True`. Releasing the logging lock allowed
`JoltTimeoutError` to propagate.

## Impact and remediation

- A timed-out command can occupy a worker indefinitely instead of reporting
  failure, while retaining task locks and test resources.
- Upgrading from 0.10.61 to 0.10.65 alone does not fix this behavior.
- Operational recovery: cancel the affected task/build; if cancellation cannot
  unwind the executor, restart the affected worker. No recovery action was
  performed during this investigation.
- Bound reader cleanup after command timeouts and add a regression test where
  an output callback cannot complete. Avoid closing a buffered stream while an
  active reader holds its lock.
- Investigate the logging-lock retention separately. Bounded joins alone may
  not restore all logging or cleanup operations if the logging lock remains
  unavailable. Consider an out-of-process watchdog as a final timeout bound.
