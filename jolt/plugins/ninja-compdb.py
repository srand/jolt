import click
import json
import os
import sys

from jolt import cache
from jolt import cli
from jolt import config
from jolt import filesystem as fs
from jolt import graph
from jolt import log
from jolt import scheduler
from jolt import utils
from jolt import loader
from jolt.hooks import TaskHook, TaskHookFactory, TaskHookRegistry
from jolt.influence import StringInfluence
from jolt.options import JoltOptions
from jolt.plugins import ninja
from jolt.tasks import TaskRegistry

log.verbose("[NinjaCompDB] Loaded")


def joltdir():
    return loader.JoltLoader.get().joltdir


def patch(command, attrib, search, replace):
    command[attrib] = command[attrib].replace(search, replace)


class CompDB(object):
    def __init__(self, path="compile_commands.json", artifact=None):
        self.commands = []
        self.attribs = {}
        if artifact:
            self.path = fs.path.join(artifact.path, path)
        else:
            self.path = path

    def metapath(self, path):
        return fs.path.join(fs.path.dirname(path), ".meta.compile_commands.json")

    def read(self, path=None):
        try:
            with open(path or self.path) as f:
                self.commands = json.load(f)
            try:
                with open(self.metapath(path or self.path)) as f:
                    self.attribs = json.load(f)
            except Exception:
                self.attribs = {}
        except OSError:
            pass

    def write(self, path=None, force=False):
        if not force and not self.commands:
            return
        with open(path or self.path, "w") as f:
            json.dump(self.commands, f, indent=2)
        with open(self.metapath(path or self.path), "w") as f:
            json.dump(self.attribs, f, indent=2)

    def annotate(self, task):
        self.attribs["joltdir"] = joltdir()
        self.attribs["cachedir"] = config.get_cachedir()

    def relocate(self, task, sandboxes=False):
        for command in self.commands:
            utils.call_and_catch(patch, command, "command", self.attribs.get("joltdir", joltdir()), joltdir())
            utils.call_and_catch(patch, command, "command", self.attribs.get("cachedir", config.get_cachedir()), config.get_cachedir())
            if sandboxes:
                utils.call_and_catch(patch, command, "command", "sandboxes/", "sandboxes-reflected/")
            utils.call_and_catch(patch, command, "directory", self.attribs.get("joltdir", joltdir()), joltdir())

    def remove_wrappers(self, task):
        for command in self.commands:
            for wrapper in [task.tools.getenv("CXXWRAP", ""), task.tools.getenv("CCWRAP", "")]:
                if command["command"].startswith(wrapper):
                    command["command"] = command["command"][len(wrapper):]

    def merge(self, db):
        self.commands.extend(db.commands)


def has_incpaths(artifact):
    return artifact.cxxinfo.incpaths.count() > 0


def stage_artifacts(artifacts, tools):
    for artifact in filter(has_incpaths, artifacts):
        tools.sandbox(artifact, incremental=True, reflect=fs.has_symlinks())


def get_task_artifacts(task):
    artifacts = []
    for dep in task.children:
        artifacts.extend(dep.artifacts)
    return task.artifacts[0], artifacts


class CompDBHooks(TaskHook):
    def task_created(self, task):
        task.task.influence.append(StringInfluence("NinjaCompDB: v3"))

    def task_postrun(self, task, deps, tools):
        if not isinstance(task.task, ninja.CXXProject):
            return
        with tools.cwd(tools.wsroot):
            utils.call_and_catch(tools.run, "ninja -f {outdir}/build.ninja -t compdb > {outdir}/compile_commands.json")

    def task_postpublish(self, task, artifact, tools):
        if isinstance(task.task, ninja.CXXProject):
            with tools.cwd(task.task.outdir):
                artifact.collect("*compile_commands.json")

        # Add information about the workspace and cachedir roots
        db = CompDB(artifact=artifact)
        db.read()
        db.annotate(task)
        db.remove_wrappers(task)
        db.write()

        if isinstance(task.task, ninja.CXXProject):
            dbpath = fs.path.join(task.task.outdir, "all_compile_commands.json")
            _, deps = get_task_artifacts(task)
            db = CompDB(dbpath)
            for dep in [artifact] + deps:
                depdb = CompDB(artifact=dep)
                depdb.read()
                depdb.relocate(task)
                db.merge(depdb)
            db.write()
            artifact.collect(dbpath, flatten=True)

    def task_finished_execution(self, task):
        if task.options.network or task.options.worker:
            return
        if not task.is_goal():
            return
        if isinstance(task.task, ninja.CXXProject):
            artifact, deps = get_task_artifacts(task)
            db = CompDB("all_compile_commands.json", artifact)
            db.read()
            db.relocate(task)
            outdir = task.tools.builddir("compdb", incremental=True)
            dbpath = fs.path.join(outdir, "all_compile_commands.json")
            db.write(dbpath, force=True)
            stage_artifacts(deps + [artifact], task.tools)

    def task_finished_download(self, task):
        self.task_finished_execution(task)


@TaskHookFactory.register
class CompDBHookFactory(TaskHookFactory):
    def create(self, env):
        return CompDBHooks()


@cli.cli.command(name="compdb")
@click.argument("task", type=str, nargs=-1, required=False, shell_complete=cli._autocomplete_tasks)
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.pass_context
def compdb(ctx, task, default):
    """
    Generate a compilation database for a task.

    Aggregates compilation databases found in artifacts of the specified task and
    its dependencies. The commands are then post-processed and localized to the
    current workspace.

    All task artifacts are sandboxed and their directory trees are recreated
    using symlinks pointing to the origin of collected files. When opening a
    file, an IDE can then follow the symlinks into the workspace instead of
    opening files in the artifact cache.

    The database must be regenerated if dependencies or the directory tree
    of an artifact change.

    """

    manifest = ctx.obj["manifest"]
    options = JoltOptions(default=default)
    acache = cache.ArtifactCache.get(options)
    TaskHookRegistry.get(options)
    executors = scheduler.ExecutorRegistry.get(options)
    registry = TaskRegistry.get()
    strategy = scheduler.DownloadStrategy(executors, acache)
    queue = scheduler.TaskQueue(strategy, acache, {})

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, acache, manifest, options, progress=True)
    dag = gb.build(task)

    try:
        with log.progress("Progress", dag.number_of_tasks(), " tasks", estimates=False, debug=False) as p:
            while dag.has_tasks() or not queue.empty():
                leafs = dag.select(lambda graph, task: task.is_ready())

                # Order the tasks by their weights to improve build times
                leafs.sort(key=lambda x: x.weight)

                while leafs:
                    task = leafs.pop()
                    queue.submit(task)

                task, error = queue.wait()
                p.update(1)

    except KeyboardInterrupt:
        print()
        log.warning("Interrupted by user")
        try:
            queue.abort()
            sys.exit(1)
        except KeyboardInterrupt:
            print()
            log.warning("Interrupted again, exiting")
            os._exit(1)

    finally:
        queue.shutdown()

    for goal in dag.goals:
        artifact, deps = get_task_artifacts(goal)
        db = CompDB("all_compile_commands.json", artifact)
        db.read()
        db.relocate(goal, sandboxes=fs.has_symlinks())
        outdir = goal.tools.builddir("compdb", incremental=True)
        dbpath = fs.path.join(outdir, "all_compile_commands.json")
        db.write(dbpath, force=True)
        stage_artifacts(deps + [artifact], goal.tools)
        log.info("Compilation DB: {}", dbpath)
