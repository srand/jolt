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
    disabled = config.getboolean("ninja-cache", "disable", False)

    tools.setenv("CCWRAP", "{} {} -- ".format(sys.executable, cli))
    tools.setenv("CXXWRAP", "{} {} -- ".format(sys.executable, cli))
    tools.setenv("JOLT_CACHEDIR", cache.ArtifactCache.get().root)
    tools.setenv("JOLT_CANONTASK", utils.canonical(self.name))
    tools.setenv("NINJACACHE_DISABLE", "1" if disabled else "0")
    tools.setenv("NINJACACHE_MAXARTIFACTS", config.getint("ninja-cache", "maxartifacts", 0))
    if log.is_verbose():
        tools.setenv("NINJACACHE_VERBOSE", "1")

    if not disabled:
        objcache = ninjacli.Cache(tools.builddir("ninja", self.incremental))
        objcache.load_manifests(tools.getenv("JOLT_CACHEDIR"), tools.getenv("JOLT_CANONTASK"))
        objcache.save()


def publish_cache(self, artifact, tools):
    with tools.cwd(self.outdir):
        m = ninjacli.LibraryManifest(tools.expand_path(".ninja.json"))
        m.read()
        m.add_library(fs.path.join(self.publishdir, fs.path.basename(self.outfiles[0])))
        m.write()
        artifact.collect(".ninja.json")

ninja.CXXLibrary.run = utils.decorate_prepend(ninja.CXXLibrary.run, run_cache)
ninja.CXXLibrary.publish = utils.decorate_prepend(ninja.CXXLibrary.publish, publish_cache)
ninja.CXXLibrary.shell = utils.decorate_prepend(ninja.CXXLibrary.shell, run_cache)
