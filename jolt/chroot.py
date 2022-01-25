#!/usr/bin/env python3

import os
import subprocess
import sys

chroot = sys.argv[1]
joltdir = os.environ["JOLTDIR"]
cachedir = os.environ["JOLTCACHEDIR"]
cwd = os.environ["PWD"]
home = os.environ["HOME"]

subprocess.run(["mount", "--rbind", "/dev", chroot + "/dev"])
subprocess.run(["mount", "--rbind", "/proc", chroot + "/proc"])

subprocess.run(["mkdir", "-p", chroot + home])
subprocess.run(["mkdir", "-p", chroot + joltdir])
subprocess.run(["mkdir", "-p", chroot + cachedir])
subprocess.run(["mount", "--rbind", home, chroot + home])
subprocess.run(["mount", "--rbind", cachedir, chroot + cachedir])
subprocess.run(["mount", "--rbind", joltdir, chroot + joltdir])

os.chroot(chroot)
sys.exit(subprocess.run(sys.argv[2:], cwd=cwd, shell=True).returncode)
