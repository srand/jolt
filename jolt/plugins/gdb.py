import click
import os
import sys

from jolt import cache
from jolt import cli
from jolt import filesystem as fs
from jolt import graph
from jolt import log
from jolt import scheduler
from jolt.error import raise_error
from jolt.error import raise_task_error_if
from jolt.hooks import TaskHookRegistry
from jolt.options import JoltOptions
from jolt.plugins import ninja
from jolt.tasks import TaskRegistry, WorkspaceResource


def has_incpaths(artifact):
    return artifact.cxxinfo.incpaths.count() > 0


def stage_artifacts(artifacts, tools):
    for artifact in filter(has_incpaths, artifacts):
        tools.sandbox(artifact, incremental=True, reflect=fs.has_symlinks())


def get_task_artifacts(task):
    artifacts = []
    for dep in task.children:
        artifacts.extend(dep.artifacts)
    return task.artifacts, artifacts


@cli.cli.command(name="gdb", context_settings={"ignore_unknown_options": True})
@click.argument("task", type=str, shell_complete=cli._autocomplete_tasks)
@click.argument("gdb-args", type=str, nargs=-1, required=False)
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.option("-mi", "--machine-interface", is_flag=True, help="Enable the machine interface for use within an IDE.")
@click.option("-nb", "--no-binary", is_flag=True,
              help="Don't load symbols from binary. Shortens startup time in IDEs where binaries are loaded through the machine interface.")
@click.pass_context
def gdb(ctx, task, default, machine_interface, no_binary, gdb_args):
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

    Additional user-defined arguments can be passed to GDB in GDB_ARGS
    immediately following the TASK name.

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
    queue = scheduler.TaskQueue(strategy, acache, {})

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, acache, manifest, options, progress=True)
    dag = gb.build([task])

    try:
        with log.progress("Progress", dag.number_of_tasks(), " tasks", estimates=False, debug=False) as p:
            while dag.has_tasks() or not queue.empty():
                leafs = dag.select(lambda graph, task: task.is_ready())

                while leafs:
                    task = leafs.pop()
                    queue.submit(task)

                task, error = queue.wait()

                # Materialize workspace resources so that
                # source code is available to the debugger.
                if isinstance(task.task, WorkspaceResource):
                    task.task.acquire_ws()

                # Unpack the task if it is not a resource task and has a custom unpack method
                if not task.is_resource():
                    if task.is_unpackable():
                        task.unpack()

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

    finally:
        queue.shutdown()

    assert len(dag.goals), "Too many tasks, can only debug one executable at a time"

    for goal in dag.goals:
        main, deps = get_task_artifacts(goal)
        stage_artifacts(main + deps, goal.tools)

        # Find an artifact with an executable
        main = [artifact for artifact in main if artifact.strings.executable.get_value()]
        raise_task_error_if(
            not main, goal, "No executable found in task artifact")
        main = main[0]

        with acache.get_context(goal):
            gdb = goal.tools.getenv("GDB", "gdb")
            gdb = goal.tools.which(gdb)
            if not gdb:
                raise_error("GDB not found in PATH")
            cmd = [gdb]
            sysroot = goal.tools.getenv("SDKTARGETSYSROOT", goal.tools.getenv("SYSROOT"))
            if sysroot:
                cmd += ["-ex", "set sysroot " + sysroot]
                cmd += ["-ex", "add-auto-load-safe-path " + sysroot]
            if fs.has_symlinks():
                cmd += ["-ex", "set substitute-path ../sandboxes/ ../sandboxes-reflected/"]
            if machine_interface:
                cmd += ["-i=mi"]
            cmd += ["-ex", "set print asm-demangle"]
            cmd += ["-ex", "set print thread-events off"]
            cmd += ["-ex", "handle SIG32 nostop noprint"]
            if not no_binary:
                cmd += [os.path.join(main.path, str(main.strings.executable))]
            cmd += gdb_args

            if isinstance(goal.task, ninja.CXXProject):
                cwd = goal.tools.wsroot
            else:
                cwd = goal.task.joltdir

            with goal.tools.environ() as env:
                os.chdir(cwd)
                os.execve(cmd[0], cmd, env)
