import argparse
import atexit
import ctypes
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time

from setproctitle import setproctitle

# Also runs as a standalone script, see launch_jobserver().
if __package__:
    from .jobserver_pressure import PressureMonitor
else:
    from jobserver_pressure import PressureMonitor


def _build_process_title(name):
    return " ".join([name] + sys.argv[1:])


class Jobserver:
    def __init__(self, path=None, slots=1, pressure=None, psi_path=None, interval=1.0):
        # The pool size is N, but we put N-1 tokens in the pipe
        # because the parent process itself occupies one slot.
        self.slots = slots
        self.path = path or tempfile.mkdtemp(prefix="jolt-jobserver-")
        self.fifo_fd = None
        self.remove_path = path is None
        os.makedirs(self.path, exist_ok=True)
        self.fifo_path = os.path.join(self.path, "jobserver_fifo")

        if os.path.exists(self.fifo_path):
            os.unlink(self.fifo_path)

        # Create the named pipe
        os.mkfifo(self.fifo_path)

        # Open RDWR so the server doesn't block while opening
        self.fifo_fd = os.open(self.fifo_path, os.O_RDWR)

        # Seed the pipe with tokens (arbitrary byte, usually '+')
        if slots > 1:
            os.write(self.fifo_fd, b'+' * (slots - 1))

        # Tokens taken out of circulation while the system is under pressure
        self.withheld = b""
        self._withheld_lock = threading.Lock()
        self._throttled = threading.Event()
        self._regulator = None
        self._regulator_stop = threading.Event()
        monitor = PressureMonitor(pressure, path=psi_path)
        if monitor.start():
            self._regulator = threading.Thread(
                target=self._regulate, args=(monitor, interval), daemon=True)
            self._regulator.start()
            # One reader per token increases the share of returned tokens
            # that are withheld. They may block in read() until the process
            # exits, so they share a file descriptor that is never closed.
            withhold_fd = os.open(self.fifo_path, os.O_RDWR)
            for _ in range(max(1, slots - 1)):
                threading.Thread(target=self._withhold, args=(withhold_fd,), daemon=True).start()

    def _regulate(self, monitor, interval):
        """ Withhold tokens while the system is under pressure. """
        try:
            while not self._regulator_stop.wait(interval):
                if monitor.update():
                    self._throttled.set()
                else:
                    self._release()
        except (OSError, ValueError):
            # Pressure information is gone. Stop regulating.
            self._release()

    def _withhold(self, fd):
        """
        Take returned tokens out of circulation while throttled.

        Clients take tokens straight from the pipe and usually read a new
        token right after returning one, so tokens rarely stay in the pipe.
        A blocking read puts this thread in line with the clients waiting
        for tokens. It gets its share of the returned tokens and the pool
        drains for as long as the pressure persists. Clients always keep
        their implicit token, so builds still make progress.
        """
        while True:
            self._throttled.wait()
            token = os.read(fd, 1)
            with self._withheld_lock:
                if self._throttled.is_set():
                    self.withheld += token
                    continue
            # Pressure dropped while waiting for the token
            os.write(fd, token)

    def _release(self):
        with self._withheld_lock:
            self._throttled.clear()
            if self._regulator_stop.is_set():
                return
            while self.withheld:
                written = os.write(self.fifo_fd, self.withheld)
                self.withheld = self.withheld[written:]

    def get_env(self):
        """Returns the environment variables required for children to connect."""
        # Using the modern FIFO syntax supported by Make 4.4+ and Ninja
        return {"MAKEFLAGS": f"--jobserver-auth=fifo:{self.fifo_path}"}

    def cleanup(self):
        """Close the FD and remove the temporary directory/pipe."""
        # Safe to call more than once, including after a previous call was
        # interrupted part way through.
        self._regulator_stop.set()
        if self._regulator is not None:
            self._regulator.join(timeout=5)
        fifo_fd, self.fifo_fd = self.fifo_fd, None
        if fifo_fd is not None:
            try:
                os.close(fifo_fd)
            except OSError:
                pass

        try:
            os.unlink(self.fifo_path)
        except FileNotFoundError:
            pass

        if os.path.exists(self.path):
            try:
                os.rmdir(self.path)
            except OSError:
                pass


class BackgroundJobserver:
    def __init__(self, process, path, parent_sentinel=None):
        self.process = process
        self.path = path
        self.fifo_path = os.path.join(path, "jobserver_fifo")
        self.parent_sentinel = parent_sentinel

    def get_env(self):
        return {"MAKEFLAGS": f"--jobserver-auth=fifo:{self.fifo_path}"}

    def cleanup(self):
        if self.parent_sentinel is not None:
            os.close(self.parent_sentinel)
            self.parent_sentinel = None

        if self.process is None:
            return

        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

        self.process = None


class AttachedJobserver:
    def __init__(self, fifo_path):
        self.fifo_path = fifo_path
        self.path = os.path.dirname(fifo_path)

    def get_env(self):
        return {"MAKEFLAGS": f"--jobserver-auth=fifo:{self.fifo_path}"}

    def cleanup(self):
        return None


def _extract_fifo_path(makeflags):
    if not makeflags:
        return None

    match = re.search(r"(?:^|\s)--jobserver-auth=fifo:([^\s]+)", makeflags)
    if match is not None:
        return match.group(1)

    return None


def _resolve_fifo_path(path=None, env=None):
    fifo_path = None

    if path:
        fifo_path = path
        if os.path.isdir(fifo_path):
            fifo_path = os.path.join(fifo_path, "jobserver_fifo")
    else:
        makeflags = (env or os.environ).get("MAKEFLAGS")
        fifo_path = _extract_fifo_path(makeflags)

    if fifo_path is None:
        return None

    fifo_path = os.path.abspath(fifo_path)
    if not os.path.exists(fifo_path):
        return None
    if not stat_is_fifo(fifo_path) and not stat_is_chardev(fifo_path):
        return None

    return fifo_path


def find_jobserver(path=None, env=None):
    """Find and attach to a jobserver started by another process."""
    fifo_path = _resolve_fifo_path(path=path, env=env)
    if fifo_path is None:
        return None
    return AttachedJobserver(fifo_path)


def stat_is_fifo(path):
    return os.path.exists(path) and stat.S_ISFIFO(os.stat(path).st_mode)


def stat_is_chardev(path):
    return os.path.exists(path) and stat.S_ISCHR(os.stat(path).st_mode)


def _create_parent_death_preexec():
    if sys.platform != "linux":
        return None

    parent_pid = os.getpid()
    parent_death_signal = signal.SIGTERM
    pr_set_pdeathsig = 1

    def _set_parent_death_signal():
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.prctl(pr_set_pdeathsig, parent_death_signal)
        if result != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))

        if os.getppid() != parent_pid:
            os.kill(os.getpid(), parent_death_signal)

    return _set_parent_death_signal


def _monitor_parent_sentinel(parent_sentinel_fd, shutdown_event):
    try:
        while os.read(parent_sentinel_fd, 1):
            pass
    except OSError:
        pass
    finally:
        try:
            os.close(parent_sentinel_fd)
        except OSError:
            pass
        shutdown_event.set()


def _monitor_parent_process_windows(parent_pid, shutdown_event):
    process_synchronize = 0x00100000
    infinite = 0xFFFFFFFF

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    process_handle = kernel32.OpenProcess(process_synchronize, False, parent_pid)
    if not process_handle:
        shutdown_event.set()
        return

    try:
        kernel32.WaitForSingleObject(process_handle, infinite)
    finally:
        kernel32.CloseHandle(process_handle)

    shutdown_event.set()


def _start_parent_liveness_monitor(parent_sentinel_fd=None, parent_pid=None):
    if parent_sentinel_fd is None and parent_pid is None:
        return None

    shutdown_event = threading.Event()
    if parent_sentinel_fd is not None:
        monitor = threading.Thread(
            target=_monitor_parent_sentinel,
            args=(parent_sentinel_fd, shutdown_event),
            daemon=True,
        )
    else:
        monitor = threading.Thread(
            target=_monitor_parent_process_windows,
            args=(parent_pid, shutdown_event),
            daemon=True,
        )
    monitor.start()
    return shutdown_event


def launch_jobserver(slots, path=None, python_executable=None, new_session=True,
                     pressure=None, psi_path=None):
    """Launch a jobserver in the background and return a shareable handle.

    ``pressure`` maps 'cpu', 'io' and 'memory' to the maximum allowed
    pressure, in microseconds of stall per second. No tokens are handed
    out while any of them is exceeded.
    """
    jobserver_path = path or tempfile.mkdtemp(prefix="jolt-jobserver-")
    command = [
        python_executable or sys.executable,
        os.path.abspath(__file__),
        "--slots", str(slots),
        "--path", jobserver_path,
    ]
    for resource, limit in (pressure or {}).items():
        if limit:
            command.extend(["--pressure-max-" + resource, str(limit)])
    if psi_path:
        command.extend(["--psi-path", psi_path])
    preexec_fn = None
    parent_sentinel = None
    popen_kwargs = {}
    if not new_session:
        preexec_fn = _create_parent_death_preexec()
        if os.name == "nt":
            command.extend(["--parent-pid", str(os.getpid())])
        else:
            parent_sentinel_fd, parent_sentinel = os.pipe()
            os.set_inheritable(parent_sentinel_fd, True)
            command.extend(["--parent-sentinel-fd", str(parent_sentinel_fd)])
            popen_kwargs["pass_fds"] = (parent_sentinel_fd,)

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            close_fds=True,
            preexec_fn=preexec_fn,
            start_new_session=new_session,
            **popen_kwargs,
        )
    finally:
        if not new_session and os.name != "nt":
            os.close(parent_sentinel_fd)

    ready_line = process.stdout.readline().strip()
    if process.stdout is not None:
        process.stdout.close()

    if not ready_line.startswith("READY "):
        if parent_sentinel is not None:
            os.close(parent_sentinel)
            parent_sentinel = None
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        raise RuntimeError("Failed to launch background jobserver: {}".format(
            ready_line or "helper process exited before becoming ready"))

    return BackgroundJobserver(process, jobserver_path, parent_sentinel=parent_sentinel)


def _serve_jobserver(path, slots, parent_sentinel_fd=None, parent_pid=None,
                     pressure=None, psi_path=None):
    stopping = False

    def _shutdown(*_args):
        # Only interrupt the helper once. When the parent dies, the sentinel
        # pipe and PR_SET_PDEATHSIG fire at about the same time, and a second
        # SystemExit raised in the middle of cleanup would leave the FIFO behind.
        nonlocal stopping
        if not stopping:
            stopping = True
            raise SystemExit(0)

    # Install signal handlers BEFORE creating the FIFO. PR_SET_PDEATHSIG is
    # armed by the launcher's preexec_fn, so a SIGTERM can in theory arrive
    # the moment this process starts running. If the default disposition
    # were still in effect when the signal hits, the helper would terminate
    # without running cleanup and leave the FIFO behind.
    handled_signals = [signal.SIGTERM, signal.SIGINT]
    if hasattr(signal, "SIGHUP"):
        handled_signals.append(signal.SIGHUP)

    for signum in handled_signals:
        signal.signal(signum, _shutdown)

    jobserver = Jobserver(path=path, slots=slots, pressure=pressure, psi_path=psi_path)

    # Belt-and-braces: ensure the FIFO and directory are removed even if the
    # helper exits via an unexpected path (e.g. an uncaught exception before
    # the finally below runs).
    atexit.register(jobserver.cleanup)

    shutdown_event = _start_parent_liveness_monitor(
        parent_sentinel_fd=parent_sentinel_fd,
        parent_pid=parent_pid,
    )

    try:
        print("READY {}".format(jobserver.fifo_path), flush=True)
        while True:
            if shutdown_event is None:
                time.sleep(3600)
            elif shutdown_event.wait(timeout=3600):
                break
    finally:
        stopping = True
        jobserver.cleanup()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run a Jolt jobserver helper process")
    parser.add_argument("--path", help="Directory that contains the jobserver FIFO")
    parser.add_argument("--parent-pid", type=int, help="PID of the launching process")
    parser.add_argument("--parent-sentinel-fd", type=int, help="Inherited pipe fd closed when the parent exits")
    parser.add_argument("--slots", type=int, required=True, help="Number of available slots")
    parser.add_argument("--pressure-max-cpu", type=float, help="Maximum CPU pressure (us stall/s)")
    parser.add_argument("--pressure-max-io", type=float, help="Maximum IO pressure (us stall/s)")
    parser.add_argument("--pressure-max-memory", type=float, help="Maximum memory pressure (us stall/s)")
    parser.add_argument("--psi-path", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    setproctitle(_build_process_title("jolt-jobserver"))

    args = _parse_args(argv)
    return _serve_jobserver(
        args.path,
        args.slots,
        parent_sentinel_fd=args.parent_sentinel_fd,
        parent_pid=args.parent_pid,
        pressure={
            "cpu": args.pressure_max_cpu,
            "io": args.pressure_max_io,
            "memory": args.pressure_max_memory,
        },
        psi_path=args.psi_path,
    )


if __name__ == "__main__":
    sys.exit(main())
