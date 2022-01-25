#!/usr/bin/env python3

import os
import subprocess
import sys

chroot = sys.argv[1]
joltdir = os.environ["JOLTDIR"]
cachedir = os.environ["JOLTCACHEDIR"]
cwd = os.environ["PWD"]

subprocess.run(["mkdir", "-p", chroot + joltdir])
subprocess.run(["mkdir", "-p", chroot + cachedir])
subprocess.run(["mount", "--rbind", joltdir, chroot + joltdir])
subprocess.run(["mount", "--rbind", cachedir, chroot + cachedir])
os.chroot(chroot)
sys.exit(subprocess.run(sys.argv[2:], cwd=cwd, shell=True).returncode)
