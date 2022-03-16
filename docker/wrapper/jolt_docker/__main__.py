#!/usr/bin/env python3

import glob
import os
import sys
import subprocess
import xml.etree.ElementTree as ET

from jolt_docker.version import __version__
from jolt_docker.version_utils import requirement


def find_manifestdir(searchdir):
    manifest = os.path.join(searchdir, "default.joltxmanifest")
    if os.path.exists(manifest):
        try:
            tree = ET.parse(manifest)
            root = tree.getroot()
            return os.path.normpath(os.path.join(searchdir, root.get("workspace", ".")))
        except FileNotFoundError:
            return searchdir

    parentdir = os.path.dirname(searchdir)
    if searchdir == parentdir:
        return None
    return find_manifestdir(parentdir)


def find_joltfiledir(searchdir):
    if glob.glob(os.path.join(searchdir, "*.jolt")):
        return searchdir

    parentdir = os.path.dirname(searchdir)
    if searchdir == parentdir:
        return None

    return find_joltdir(parentdir)


# Aka workspace directory
def find_joltdir(searchdir):
    manifestdir = find_manifestdir(searchdir)
    if manifestdir:
        return manifestdir
    return find_joltfiledir(searchdir)


def find_version(joltdir):
    manifest = os.path.join(joltdir, "default.joltxmanifest")
    try:
        tree = ET.parse(manifest)
        root = tree.getroot()
        verstr = root.get("version")
        if not verstr:
            return "latest"
        return str(requirement(verstr).required())
    except FileNotFoundError:
        return "latest"


def find_image():
    manifest = os.path.join(joltdir, "default.joltxmanifest")
    try:
        tree = ET.parse(manifest)
        root = tree.getroot()
        return root.get("image", "robrt/jolt")
    except FileNotFoundError:
        return "robrt/jolt"


def verbose(fmt, *args, **kwargs):
    if "-vv" in sys.argv:
        print("[  DEBUG] " + fmt.format(*args, **kwargs))


home = os.getenv("HOME")
cwd = os.getcwd()
joltdir = find_joltdir(os.getcwd()) or cwd
version = find_version(joltdir)
image = find_image()
image = f"{image}:{version}"
verbose(f"Using image '{image}'")
uid = os.getuid()
gid = os.getgid()
groups = os.getgroups()
environ = []
volumes = []

if home:
    volumes += [f"{home}/.cache/jolt:{home}/.cache/jolt"]
    volumes += [f"{home}/.config/jolt:{home}/.config/jolt"]
    volumes += [f"{home}/.jolt:{home}/.jolt"]
    environ += [f"HOME={home}"]

if cwd:
    volumes += [f"{joltdir}:{joltdir}"]

if os.name == "posix":
    volumes += ["/etc/group:/etc/group:ro"]
    volumes += ["/etc/gshadow:/etc/gshadow:ro"]
    volumes += ["/etc/passwd:/etc/passwd:ro"]
    volumes += ["/etc/shadow:/etc/shadow:ro"]

    if os.path.exists("/var/run/docker.sock"):
        volumes += ["/var/run/docker.sock:/var/run/docker.sock"]


# Build command line

cmd = ["docker", "run", "-i", "--privileged", "--rm", "-u", f"{uid}:{gid}", "-w", cwd]
if sys.stdin.isatty() and sys.stdout.isatty():
    cmd += ["-t"]
for volume in volumes:
    cmd += ["-v", volume]
for group in groups:
    cmd += ["--group-add", str(group)]
cmd += [image]
cmd += sys.argv[1:]


def main():
    if "--version" in sys.argv:
        print(f"jolt, version {__version__}")
        sys.exit(0)
    verbose("Running: {} (CWD: {})", " ".join(cmd), cwd)
    sys.exit(subprocess.call(cmd))

if __name__ == "__main__":
    main()
