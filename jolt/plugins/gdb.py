import click
import json
import os
import sys
import subprocess

from jolt import cache
from jolt import cli
from jolt import config
from jolt import filesystem as fs
from jolt import graph
from jolt import log
from jolt import scheduler
from jolt import utils
from jolt import loader
from jolt.error import raise_task_error_if
from jolt.hooks import TaskHook, TaskHookFactory, TaskHookRegistry
from jolt.influence import StringInfluence
from jolt.options import JoltOptions
from jolt.plugins import ninja
from jolt.tasks import TaskRegistry, WorkspaceResource


def has_incpaths(artifact):
    return artifact.cxxinfo.incpaths.count() > 0


def stage_artifacts(artifacts, tools):
    for artifact in filter(has_incpaths, artifacts):
        tools.sandbox(artifact, incremental=True)


def get_task_artifacts(task, artifact=None):
    acache = cache.ArtifactCache.get()
    artifact = artifact or acache.get_artifact(task)
    return artifact, [acache.get_artifact(dep) for dep in task.children]


@cli.cli.command(name="gdb")
@click.argument("task", type=str, nargs=-1, required=False, shell_complete=cli._autocomplete_tasks)
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.option("-mi", "--machine-interface", is_flag=True, help="Enable the machine interface for use within an IDE.")
@click.pass_context
def gdb(ctx, task, default, machine_interface):
    """
    Launch gdb with an executable from a task artifact.

    The executable to debug must be described in the task's artifact
    metadata using the ``artifact.strings.executable`` variable. This
    is provided by default if the task is a compilation task derived from
    :class:`ninja.CXXExecutable`.

    Before starting GDB, the command downloads all the task's dependencies
    and ensures that its workspace resources are present in the workspace.
    This allows GDB to find source files in both artifacts and SCM
    repositories.

    The command automatically sets the sysroot property in GDB
    if any of the environment variables ``SYSROOT`` or ``SDKTARGETSYSROOT``
    is set in the execution environment of the task.

    The ``-mi`` argument should typically be passed if the command is
    launched from within an IDE to allow the IDE to parse and interpret
    output from GDB.

    """

    if machine_interface:
        log.enable_gdb()

    manifest = ctx.obj["manifest"]
    options = JoltOptions(default=default)
    acache = cache.ArtifactCache.get(options)
    TaskHookRegistry.get(options)
    executors = scheduler.ExecutorRegistry.get(options)
    registry = TaskRegistry.get()
    strategy = scheduler.DownloadStrategy(executors, acache)
    queue = scheduler.TaskQueue(strategy)

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, manifest, options, progress=True)
    dag = gb.build(task)

    try:
        with log.progress("Progress", dag.number_of_tasks(), " tasks", estimates=False, debug=False) as p:
            while dag.has_tasks():
                leafs = dag.select(lambda graph, task: task.is_ready())

                while leafs:
                    task = leafs.pop()
                    queue.submit(acache, task)

                task, error = queue.wait()

                # Materialize workspace resources so that
                # source code is available to the debugger.
                if isinstance(task.task, WorkspaceResource):
                    task.task.acquire()

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
    except Exception as e:
        log.set_interactive(True)
        raise e

    assert len(dag.goals), "Too many tasks, can only debug one executable at a time"

    for goal in dag.goals:
        artifact, deps = get_task_artifacts(goal)
        stage_artifacts(deps + [artifact], goal.tools)

        raise_task_error_if(
            artifact.strings.executable.get_value() is None,
            goal, "No executable found in task artifact")

        with acache.get_context(goal) as context:
            gdb = goal.tools.getenv("GDB", "gdb")
            cmd = [gdb]
            sysroot = goal.tools.getenv("SDKTARGETSYSROOT", goal.tools.getenv("SYSROOT"))
            if sysroot:
                cmd += ["-ex", "set sysroot " + sysroot]
                cmd += ["-ex", "add-auto-load-safe-path " + sysroot]
            if machine_interface:
                cmd += ["-i=mi"]
            cmd += ["-ex", "set print asm-demangle"]
            cmd += ["-ex", "set print thread-events off"]
            cmd += ["-ex", "handle SIG32 nostop noprint"]
            cmd += [os.path.join(artifact.path, str(artifact.strings.executable))]

            if isinstance(goal.task, ninja.CXXProject):
                cwd = goal.tools.builddir("ninja", incremental=True)
            else:
                cwd = goal.task.joltdir

            with goal.tools.environ() as env:
                subprocess.call(cmd, env=env, cwd=cwd)
