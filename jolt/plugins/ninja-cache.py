import functools
import sys

from jolt import cache
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.hooks import TaskHook, TaskHookFactory
from jolt.influence import StringInfluence
from jolt.plugins import ninja
from jolt.plugins import ninjacli

log.verbose("[NinjaCache] Loaded")


class CacheHooks(TaskHook):
    def task_created(self, task):
        if not isinstance(task.task, ninja.CXXLibrary) or task.task.shared:
            return
        task.task.influence.append(StringInfluence("NinjaCache"))
        task.task._write_ninja_cache = functools.partial(self.task_post_ninja_file, task)

    def task_post_ninja_file(self, task, deps, tools):
        if not isinstance(task.task, ninja.CXXLibrary) or task.task.shared:
            return

        cli = fs.path.join(fs.path.dirname(__file__), "ninjacli.py")
        disabled = config.getboolean("ninja-cache", "disable", False)

        tools.setenv("CCWRAP", "{} {} -- ".format(sys.executable, cli))
        tools.setenv("CXXWRAP", "{} {} -- ".format(sys.executable, cli))
        tools.setenv("JOLT_CACHEDIR", cache.ArtifactCache.get().root)
        tools.setenv("JOLT_CANONTASK", utils.canonical(task.task.name))
        tools.setenv("NINJACACHE_DISABLE", "1" if disabled else "0")
        tools.setenv("NINJACACHE_MAXARTIFACTS", config.getint("ninja-cache", "maxartifacts", 0))
        if log.is_verbose():
            tools.setenv("NINJACACHE_VERBOSE", "1")

        if not disabled:
            objcache = ninjacli.Cache(tools.builddir("ninja", task.task.incremental))
            objcache.load_manifests(tools.getenv("JOLT_CACHEDIR"), tools.getenv("JOLT_CANONTASK"))
            objcache.save()

    def task_postpublish(self, task, artifact, tools):
        if not isinstance(task.task, ninja.CXXLibrary) or task.task.shared:
            return
        with tools.cwd(task.task.outdir):
            m = ninjacli.LibraryManifest(tools.expand_path(".ninja.json"))
            m.read()
            if hasattr(artifact.strings, "library"):
                m.add_library(fs.path.join(
                    task.task.publishdir,
                    fs.path.basename(str(artifact.strings.library))))
            m.write()
            artifact.collect(".ninja.json")


@TaskHookFactory.register
class CacheHookFactory(TaskHookFactory):
    def create(self, env):
        return CacheHooks()
