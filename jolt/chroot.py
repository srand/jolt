"""
Helper module that sets up a mount and user namespace before executing
a command. The helper primarily bypasses the restriction on creating
namespaces from multithreaded applications (which Jolt is).
"""
import argparse
from ctypes import CDLL, c_char_p
import multiprocessing
import os
import shutil
import sys

libc = CDLL("libc.so.6")

CLONE_NEWNS = 0x00020000
CLONE_NEWUSER = 0x10000000

MS_RDONLY = 1
MS_BIND = 4096
MS_REC = 16384


def mount_bind(src, dst, ro=False):
    src = os.path.normpath(src)
    dst = os.path.normpath(dst)

    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            with open(dst, "a"):
                pass

    assert libc.mount(
        c_char_p(src.encode("utf-8")),
        c_char_p(dst.encode("utf-8")),
        None,
        MS_BIND | MS_REC | (MS_RDONLY if ro else 0),
        None) == 0


def mount_tmpfs(path):
    assert libc.mount(
        c_char_p("none".encode("utf-8")),
        c_char_p(path.encode("utf-8")),
        c_char_p("tmpfs".encode("utf-8")),
        0, None) == 0, f"Failed to mount tmpfs at '{path}'"


def main():
    parser = argparse.ArgumentParser(
        prog='chroot',
        description='Runs a command in a chroot using linux namespaces')
    parser.add_argument('command', nargs='+')
    parser.add_argument('-b', '--bind', nargs="*")
    parser.add_argument('-c', '--chroot', required=True)
    parser.add_argument('-d', '--chdir')
    parser.add_argument('--shell', default="True")
    args = parser.parse_args()

    cwd = os.getcwd()
    gid = os.getegid()
    uid = os.geteuid()
    gidmap = [gid, gid, 1]
    uidmap = [uid, uid, 1]
    gidmap = [str(i) for i in gidmap]
    uidmap = [str(i) for i in uidmap]
    newgidmap = "/usr/bin/newgidmap"
    newuidmap = "/usr/bin/newuidmap"

    sem = multiprocessing.Semaphore(0)
    parent = os.getpid()
    child = os.fork()
    if child == 0:
        sem.acquire()
        pid = os.fork()
        if pid == 0:
            os.execve(newuidmap, [newuidmap, str(parent)] + uidmap, {})
            os._exit(1)
        _, status = os.waitpid(pid, 0)
        assert status == 0, f"Failed to map UIDs: newuidmap exit status: {status}"
        os.execve(newgidmap, [newgidmap, str(parent)] + gidmap, {})
        os._exit(1)

    assert libc.unshare(CLONE_NEWNS | CLONE_NEWUSER) == 0
    sem.release()
    _, status = os.waitpid(child, 0)
    assert status == 0, f"Failed to map GIDs: newgidmap exit status: {status}"

    mount_tmpfs("/mnt")
    mount_bind(args.chroot, "/mnt", True)
    mount_bind("/proc", "/mnt/proc", True)

    for path in args.bind or []:
        mount_bind(path, os.path.join("/mnt", os.path.relpath(path, "/")))

    os.chroot("/mnt")
    os.chdir(args.chdir or cwd)

    if args.shell in ["True", "true"]:
        os.execve("/bin/sh", ["sh", "-c", " ".join(args.command)], os.environ)
    else:
        exe = shutil.which(args.command[0])
        os.execve(exe, args.command, os.environ)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        os._exit(1)
