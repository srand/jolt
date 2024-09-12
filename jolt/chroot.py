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


def prepare_bind(root, src):
    src = os.path.normpath(src)
    dst = os.path.normpath(os.path.join(root, src.lstrip("/")))

    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w"):
            pass


def mount_bind(src, dst, ro=False):
    src = os.path.normpath(src)
    dst = os.path.normpath(dst)

    assert libc.mount(
        c_char_p(src.encode("utf-8")),
        c_char_p(dst.encode("utf-8")),
        None,
        MS_BIND | MS_REC | (MS_RDONLY if ro else 0),
        None) == 0, f"Failed to bind mount {src}"


def mount_overlay(src, binds, dst, temp):
    src = os.path.normpath(src)
    dst = os.path.normpath(dst)

    upper = os.path.join(temp, "upper")
    work = os.path.join(temp, "work")
    os.makedirs(upper, exist_ok=True)
    os.makedirs(work, exist_ok=True)

    return libc.mount(
        c_char_p("none".encode("utf-8")),
        c_char_p(dst.encode("utf-8")),
        c_char_p("overlay".encode("utf-8")),
        0,
        f"lowerdir={src}:{binds},upperdir={upper},workdir={work}".encode("utf-8")) == 0


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
    parser.add_argument('-t', '--temp', required=True)
    parser.add_argument('-c', '--chroot', required=True)
    parser.add_argument('-d', '--chdir')
    parser.add_argument('--shell', default="True")
    args = parser.parse_args()

    # Prepare bind mount targets outside userns
    for path in args.bind or []:
        prepare_bind(args.temp, path)

    cwd = os.getcwd()
    gid = os.getegid()
    uid = os.geteuid()
    gidmap = [gid, gid, 1]
    uidmap = [uid, uid, 1]
    gidmap = [str(i) for i in gidmap]
    uidmap = [str(i) for i in uidmap]

    newgidmap = shutil.which("newgidmap") or shutil.which("/usr/bin/newgidmap")
    newuidmap = shutil.which("newuidmap") or shutil.which("/usr/bin/newuidmap")

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
    if not mount_overlay(args.chroot, args.temp, "/mnt", "/mnt"):
        mount_bind(args.chroot, "/mnt", True)
    mount_bind("/proc", "/mnt/proc", True)

    for path in args.bind or []:
        mount_bind(path, os.path.join("/mnt", os.path.relpath(path, "/")))

    os.chroot("/mnt")
    os.chdir(args.chdir or cwd)

    # Adjust PATH to include standard paths, if missing
    path = os.environ.get("PATH", None)
    if path is None:
        path = "/usr/local/bin:/usr/bin:/bin"
    else:
        path = path.split(os.pathsep)
        if "/usr/local/bin" not in path:
            path.append("/usr/local/bin")
        if "/usr/bin" not in path:
            path.append("/usr/bin")
        if "/bin" not in path:
            path.append("/bin")
        path = os.pathsep.join(path)
    os.environ["PATH"] = path

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
