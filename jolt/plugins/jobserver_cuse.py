#!/usr/bin/env python3
"""Python jobserver CUSE device implementation.

This script implements a CUSE jobserver device using ctypes bindings to libfuse3.
It provides /dev/jobserver, tracks checked-out job server tokens per open file description,
and returns leaked tokens when a client closes its file descriptor.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import signal
import sys
from dataclasses import dataclass
from typing import Any, Optional


POLLIN = 0x001
POLLOUT = 0x004
O_NONBLOCK = os.O_NONBLOCK


fuse_req_t = ctypes.c_void_p
fuse_session_p = ctypes.c_void_p
fuse_pollhandle_p = ctypes.c_void_p


class FuseCtx(ctypes.Structure):
    _fields_ = [
        ("uid", ctypes.c_uint),
        ("gid", ctypes.c_uint),
        ("pid", ctypes.c_int),
        ("umask", ctypes.c_uint),
    ]


class FuseFileInfo(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_int),
        ("writepage", ctypes.c_uint, 1),
        ("direct_io", ctypes.c_uint, 1),
        ("keep_cache", ctypes.c_uint, 1),
        ("flush", ctypes.c_uint, 1),
        ("nonseekable", ctypes.c_uint, 1),
        ("flock_release", ctypes.c_uint, 1),
        ("cache_readdir", ctypes.c_uint, 1),
        ("noflush", ctypes.c_uint, 1),
        ("padding", ctypes.c_uint, 24),
        ("padding2", ctypes.c_uint, 32),
        ("fh", ctypes.c_uint64),
        ("lock_owner", ctypes.c_uint64),
        ("poll_events", ctypes.c_uint32),
    ]


class FuseArgs(ctypes.Structure):
    _fields_ = [
        ("argc", ctypes.c_int),
        ("argv", ctypes.POINTER(ctypes.c_char_p)),
        ("allocated", ctypes.c_int),
    ]


class CuseInfo(ctypes.Structure):
    _fields_ = [
        ("dev_major", ctypes.c_uint),
        ("dev_minor", ctypes.c_uint),
        ("dev_info_argc", ctypes.c_uint),
        ("dev_info_argv", ctypes.POINTER(ctypes.c_char_p)),
        ("flags", ctypes.c_uint),
    ]


OPEN_CB = ctypes.CFUNCTYPE(None, fuse_req_t, ctypes.POINTER(FuseFileInfo))
RELEASE_CB = ctypes.CFUNCTYPE(None, fuse_req_t, ctypes.POINTER(FuseFileInfo))
READ_CB = ctypes.CFUNCTYPE(
    None, fuse_req_t, ctypes.c_size_t, ctypes.c_long, ctypes.POINTER(FuseFileInfo)
)
WRITE_CB = ctypes.CFUNCTYPE(
    None,
    fuse_req_t,
    ctypes.c_char_p,
    ctypes.c_size_t,
    ctypes.c_long,
    ctypes.POINTER(FuseFileInfo),
)
POLL_CB = ctypes.CFUNCTYPE(
    None, fuse_req_t, ctypes.POINTER(FuseFileInfo), fuse_pollhandle_p
)
INTERRUPT_CB = ctypes.CFUNCTYPE(None, fuse_req_t, ctypes.c_void_p)


class CuseLowlevelOps(ctypes.Structure):
    _fields_ = [
        ("init", ctypes.c_void_p),
        ("init_done", ctypes.c_void_p),
        ("destroy", ctypes.c_void_p),
        ("open", OPEN_CB),
        ("read", READ_CB),
        ("write", WRITE_CB),
        ("flush", ctypes.c_void_p),
        ("release", RELEASE_CB),
        ("fsync", ctypes.c_void_p),
        ("ioctl", ctypes.c_void_p),
        ("poll", POLL_CB),
    ]


@dataclass(eq=False)
class Client:
    pid: int
    balance: int = 0
    refcount: int = 0


@dataclass
class Reader:
    req: Optional[int]
    client: Client


@dataclass
class Poller:
    ph: int


class JobServer:
    def __init__(self, tokens: Optional[int] = None, devname: str = "jobserver") -> None:
        self.tokens = tokens if tokens is not None else (os.cpu_count() or 1) + 1
        self.devname = devname
        self.clients: dict[int, Client] = {}
        self.readers: list[Reader] = []
        self.pollers: list[Poller] = []
        self.client_handles: dict[int, Client] = {}
        self.lib = self._load_fuse()
        self._configure_fuse_symbols()
        self._open_cb = OPEN_CB(self.dev_open)
        self._release_cb = RELEASE_CB(self.dev_release)
        self._read_cb = READ_CB(self.dev_read)
        self._write_cb = WRITE_CB(self.dev_write)
        self._poll_cb = POLL_CB(self.dev_poll)
        self._interrupt_cb = INTERRUPT_CB(self.dev_interrupt)
        self.ops = CuseLowlevelOps(
            None,
            None,
            None,
            self._open_cb,
            self._read_cb,
            self._write_cb,
            None,
            self._release_cb,
            None,
            None,
            self._poll_cb,
        )

    @staticmethod
    def _load_fuse() -> ctypes.CDLL:
        libname = ctypes.util.find_library("fuse3") or ctypes.util.find_library("fuse")
        if not libname:
            raise RuntimeError("could not find libfuse3")
        return ctypes.CDLL(libname, use_errno=True)

    def _configure_fuse_symbols(self) -> None:
        self.lib.fuse_req_ctx.argtypes = [fuse_req_t]
        self.lib.fuse_req_ctx.restype = ctypes.POINTER(FuseCtx)

        self.lib.fuse_reply_err.argtypes = [fuse_req_t, ctypes.c_int]
        self.lib.fuse_reply_err.restype = ctypes.c_int

        self.lib.fuse_reply_open.argtypes = [fuse_req_t, ctypes.POINTER(FuseFileInfo)]
        self.lib.fuse_reply_open.restype = ctypes.c_int

        self.lib.fuse_reply_buf.argtypes = [fuse_req_t, ctypes.c_char_p, ctypes.c_size_t]
        self.lib.fuse_reply_buf.restype = ctypes.c_int

        self.lib.fuse_reply_write.argtypes = [fuse_req_t, ctypes.c_size_t]
        self.lib.fuse_reply_write.restype = ctypes.c_int

        self.lib.fuse_reply_poll.argtypes = [fuse_req_t, ctypes.c_uint]
        self.lib.fuse_reply_poll.restype = ctypes.c_int

        self.lib.fuse_req_interrupt_func.argtypes = [fuse_req_t, INTERRUPT_CB, ctypes.c_void_p]
        self.lib.fuse_req_interrupt_func.restype = None

        self.lib.fuse_lowlevel_notify_poll.argtypes = [fuse_pollhandle_p]
        self.lib.fuse_lowlevel_notify_poll.restype = ctypes.c_int

        self.lib.fuse_pollhandle_destroy.argtypes = [fuse_pollhandle_p]
        self.lib.fuse_pollhandle_destroy.restype = None

        self.lib.cuse_lowlevel_new.argtypes = [
            ctypes.POINTER(FuseArgs),
            ctypes.POINTER(CuseInfo),
            ctypes.POINTER(CuseLowlevelOps),
            ctypes.c_void_p,
        ]
        self.lib.cuse_lowlevel_new.restype = fuse_session_p

        self.lib.fuse_session_mount.argtypes = [fuse_session_p, ctypes.c_char_p]
        self.lib.fuse_session_mount.restype = ctypes.c_int

        self.lib.fuse_session_loop.argtypes = [fuse_session_p]
        self.lib.fuse_session_loop.restype = ctypes.c_int

        self.lib.fuse_session_unmount.argtypes = [fuse_session_p]
        self.lib.fuse_session_unmount.restype = None

        self.lib.fuse_session_destroy.argtypes = [fuse_session_p]
        self.lib.fuse_session_destroy.restype = None

    @staticmethod
    def log(message: str, *args: object) -> None:
        if args:
            message = message % args
        print(message, file=sys.stderr, end="")

    def client_ref(self, pid: int) -> Client:
        client = self.clients.get(pid)
        if client is None:
            client = Client(pid=pid)
            self.clients[pid] = client
        client.refcount += 1
        self.client_handles[id(client)] = client
        return client

    def client_del(self, client: Client) -> None:
        self.clients.pop(client.pid, None)
        self.client_handles.pop(id(client), None)

    def reader_enqueue(self, req: fuse_req_t, client: Client) -> None:
        self.readers.append(Reader(req=req.value if hasattr(req, "value") else int(req), client=client))

    def poller_enqueue(self, ph: fuse_pollhandle_p) -> None:
        self.pollers.append(Poller(ph=ph.value if hasattr(ph, "value") else int(ph)))

    def wake_readers(self) -> None:
        while self.readers and self.tokens:
            reader = self.readers.pop(0)
            if reader.req:
                reader.client.balance += 1
                self.tokens -= 1
                self.lib.fuse_reply_buf(fuse_req_t(reader.req), b".", 1)

        if not self.tokens:
            return

        while self.pollers:
            poller = self.pollers.pop(0)
            ph = fuse_pollhandle_p(poller.ph)
            self.lib.fuse_lowlevel_notify_poll(ph)
            self.lib.fuse_pollhandle_destroy(ph)

    def dev_open(self, req: fuse_req_t, fi: Any) -> None:
        ctx = self.lib.fuse_req_ctx(req).contents
        if ctx.pid == 0:
            self.log("error: client pid is 0; run container with --pid=host\n")
            self.lib.fuse_reply_err(req, errno.ENOTSUP)
            self.lib.fuse_session_exit(self.session)
            return
        client = self.client_ref(ctx.pid)
        fi.contents.fh = id(client)
        self.lib.fuse_reply_open(req, fi)

    def dev_release(self, req: fuse_req_t, fi: Any) -> None:
        client = self.client_handles.get(int(fi.contents.fh))
        if client is None:
            self.lib.fuse_reply_err(req, errno.EBADF)
            return

        client.refcount -= 1
        if client.refcount == 0:
            self.log("[RELEASE] final token balance %d for pid %d\n", client.balance, client.pid)
            self.tokens += client.balance
            self.wake_readers()
            self.client_del(client)
        self.lib.fuse_reply_err(req, 0)

    def dev_interrupt(self, req: fuse_req_t, _data: ctypes.c_void_p) -> None:
        req_value = req.value if hasattr(req, "value") else int(req)
        for reader in self.readers:
            if reader.req == req_value:
                reader.req = None
                self.lib.fuse_reply_err(req, errno.EINTR)
                return

    def dev_read(
        self,
        req: fuse_req_t,
        size: int,
        _off: int,
        fi: Any,
    ) -> None:
        size = 1 if size else 0
        client = self.client_handles.get(int(fi.contents.fh))
        if client is None:
            self.lib.fuse_reply_err(req, errno.EBADF)
            return

        if self.tokens >= size:
            client.balance += size
            self.tokens -= size
            self.lib.fuse_reply_buf(req, b".", size)
        elif fi.contents.flags & O_NONBLOCK:
            self.lib.fuse_reply_err(req, errno.EAGAIN)
        else:
            self.reader_enqueue(req, client)
            self.lib.fuse_req_interrupt_func(req, self._interrupt_cb, None)

    def dev_write(
        self,
        req: fuse_req_t,
        _buf: ctypes.c_char_p,
        size: int,
        _off: int,
        fi: Any,
    ) -> None:
        size = 1 if size else 0
        client = self.client_handles.get(int(fi.contents.fh))
        if client is None:
            self.lib.fuse_reply_err(req, errno.EBADF)
            return

        if client.balance >= size:
            client.balance -= size
            self.tokens += size
            self.wake_readers()
        else:
            self.log("[WRITE] ignoring extra token from pid %d\n", client.pid)
        self.lib.fuse_reply_write(req, size)

    def dev_poll(
        self,
        req: fuse_req_t,
        fi: Any,
        ph: fuse_pollhandle_p,
    ) -> None:
        events = fi.contents.poll_events & (POLLIN | POLLOUT)
        if not self.tokens:
            events &= ~POLLIN
            if not events:
                self.poller_enqueue(ph)
        self.lib.fuse_reply_poll(req, events)

    def run(self, argv: list[str]) -> int:
        cuse_fd = os.open("/dev/cuse", os.O_RDWR)
        mountpoint = f"/dev/fd/{cuse_fd}".encode()

        argv_bytes = [arg.encode() for arg in argv]
        argv_array = (ctypes.c_char_p * len(argv_bytes))(*argv_bytes)
        fuse_args = FuseArgs(len(argv_bytes), argv_array, 0)

        devname = ctypes.c_char_p(b"DEVNAME=" + self.devname.encode())
        dev_info = (ctypes.c_char_p * 1)(devname)
        cuse_info = CuseInfo(0, 0, 1, dev_info, 0)

        session = self.lib.cuse_lowlevel_new(
            ctypes.byref(fuse_args), ctypes.byref(cuse_info), ctypes.byref(self.ops), None
        )
        if not session:
            return 1

        try:
            if self.lib.fuse_session_mount(session, mountpoint):
                return 1
            return 1 if self.lib.fuse_session_loop(session) else 0
        finally:
            self.lib.fuse_session_unmount(session)
            self.lib.fuse_session_destroy(session)
            os.close(cuse_fd)


def parse_args(argv: list[str]) -> tuple[int, list[str]]:
    default_tokens = int(os.getenv("JOLT_JOBSERVER_TOKEN_COUNT", os.cpu_count() or 1)) + 1
    fuse_argv = [argv[0]]
    rest = argv[1:]

    if rest and not rest[0].startswith("-"):
        try:
            tokens = int(rest[0])
        except ValueError:
            print(f"Usage: {argv[0]} [num_tokens] [fuse options...]", file=sys.stderr)
            raise SystemExit(2)
        if tokens < 1:
            print("num_tokens must be a positive integer", file=sys.stderr)
            raise SystemExit(2)
        rest = rest[1:]
    else:
        tokens = default_tokens

    fuse_argv.extend(rest)
    return tokens, fuse_argv


def main(argv: list[str]) -> int:
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        tokens, fuse_argv = parse_args(argv)
        devname = os.getenv("JOLT_JOBSERVER_DEVNAME", "jobserver")
        print(f"Starting jobserver with {tokens} tokens on /dev/{devname}", file=sys.stderr)
        return JobServer(tokens, devname).run(fuse_argv)
    except OSError as exc:
        print(f"{exc.filename or 'jobserver'}: {exc.strerror}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
