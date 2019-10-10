import click
import hashlib
import json
import os
import sys
import subprocess

from jolt import cache
from jolt import config
from jolt import error
from jolt import filesystem as fs
from jolt import log
from jolt import tools
from jolt import utils
from jolt.plugins import ninja
from jolt.plugins import ninjacli

log.verbose("[NinjaCache] Loaded")


def run_cache(self, artifact, tools):
    cli = fs.path.join(fs.path.dirname(__file__), "ninjacli.py")
    disabled = "1" if config.getboolean("ninja-cache", "disable", False) else "0"
    tools.setenv("CCWRAP", "{} {} -- ".format(sys.executable, cli))
    tools.setenv("CXXWRAP", "{} {} -- ".format(sys.executable, cli))
    tools.setenv("JOLT_CACHEDIR", cache.ArtifactCache.get().root)
    tools.setenv("JOLT_CANONTASK", utils.canonical(self.name))
    tools.setenv("NINJACACHE_DISABLE", disabled)

def publish_cache(self, artifact, tools):
    with tools.cwd(self.outdir):
        m = ninjacli.LibraryManifest(tools.expand_path(".ninja.json"))
        m.read()
        m.add_library(fs.path.join(self.publishdir, fs.path.basename(self.outfiles[0])))
        m.write()
        artifact.collect(".ninja.json")

def _decorate_publish(publish):
    def _publish(self, artifact, tools):
        publish_cache(self, artifact, tools)
        publish(self, artifact, tools)
    return _publish

def _decorate_run(run):
    def _run(self, artifact, tools):
        run_cache(self, artifact, tools)
        run(self, artifact, tools)
    return _run

def _decorate_shell(shell):
    def _shell(self, artifact, tools):
        run_cache(self, artifact, tools)
        shell(self, artifact, tools)
    return _shell

ninja.CXXLibrary.run = _decorate_run(ninja.CXXLibrary.run)
ninja.CXXLibrary.publish = _decorate_publish(ninja.CXXLibrary.publish)
ninja.CXXLibrary.shell = _decorate_shell(ninja.CXXLibrary.shell)

