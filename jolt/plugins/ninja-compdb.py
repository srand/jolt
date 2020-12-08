import click
import json
import os
import sys

from jolt import cache
from jolt import cli
from jolt import config
from jolt import graph
from jolt import log
from jolt import scheduler
from jolt import utils
from jolt.error import raise_task_error_if
from jolt.hooks import TaskHook, TaskHookFactory, TaskHookRegistry
from jolt.influence import StringInfluence
from jolt.options import JoltOptions
from jolt.plugins import ninja
from jolt.tasks import TaskRegistry
from jolt.tools import Tools

log.verbose("[NinjaCompDB] Loaded")


class CompDBHooks(TaskHook):
    def task_created(self, task):
        task.task.influence.append(StringInfluence("NinjaCompDB"))

    def task_postrun(self, task, deps, tools):
        if not isinstance(task.task, ninja.CXXProject):
            return

        with tools.cwd(task.task.outdir):
            utils.call_and_catch(tools.run, "ninja -f build.ninja -t compdb > compile_commands.json")

    def task_postpublish(self, task, artifact, tools):
        if isinstance(task.task, ninja.CXXProject):
            with tools.cwd(task.task.outdir):
                artifact.collect("*compile_commands.json")

        with tools.cwd(artifact.path):
            if not tools.glob("compile_commands.json"):
                return

            # Add information about the workspace and cachedir roots
            with open(tools.expand_path("compile_commands.json")) as f:
                commands = json.load(f)
            for command in commands:
                command["joltdir"] = task.task.joltdir
                command["cachedir"] = config.get_cachedir()
            with open(tools.expand_path("compile_commands.json"), "w") as f:
                json.dump(commands, f, indent=2)


def patch(command, target, search, replace):
    command[target] = command[target].replace(
        command[search], replace)


@TaskHookFactory.register
class CompDBHookFactory(TaskHookFactory):
    def create(self, env):
        return CompDBHooks()


@cli.cli.command(name="compdb")
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=cli._autocomplete_tasks)
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
    hooks = TaskHookRegistry.get(options)
    executors = scheduler.ExecutorRegistry.get(options)
    registry = TaskRegistry.get()
    strategy = scheduler.DownloadStrategy(executors, acache)
    queue = scheduler.TaskQueue(strategy)
    reflect = True

    # Symlinks are problematic on older versions of Windows.
    # On those, we create regular copied sandboxes instead.
    if os.name == "nt" and sys.getwindowsversion().major < 10:
        reflect = False

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, manifest, options, progress=True)
    dag = gb.build(task)

    try:
        with log.progress("Progress", dag.number_of_tasks(), " tasks", estimates=False, debug=False) as p:
            while dag.has_tasks():
                leafs = dag.select(lambda graph, task: task.is_ready())

                # Order the tasks by their weights to improve build times
                leafs.sort(key=lambda x: x.weight)

                while leafs:
                    task = leafs.pop()
                    queue.submit(acache, task)

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

    for goal in dag.goals:
        with acache.get_context(goal) as context:
            all_commands = []
            outdir = goal.tools.builddir("ninja", True)

            artifacts = [acache.get_artifact(goal)]
            artifacts += [artifact for name, artifact in context.items()]

            # Load commands from artifacts
            for artifact in artifacts:
                try:
                    with goal.tools.cwd(artifact.path):
                        with open(goal.tools.expand_path("compile_commands.json")) as f:
                            data = f.read()
                            if reflect:
                                data = data.replace("sandbox-", "sandbox-reflect-")
                            commands = json.loads(data)
                    for command in commands:
                        utils.call_and_catch(patch, command, "command", "joltdir", task.task.joltdir)
                        utils.call_and_catch(patch, command, "command", "cachedir", config.get_cachedir())
                        utils.call_and_catch(patch, command, "directory", "joltdir", task.task.joltdir)
                    all_commands.extend(commands)
                except KeyboardInterrupt as e:
                    raise e
                except Exception:
                    pass
                goal.tools.sandbox(artifact, incremental=True, reflect=reflect)

            # Write result
            with goal.tools.cwd(outdir):
                with open(goal.tools.expand_path("all_compile_commands.json"), "w") as f:
                    json.dump(all_commands, f, indent=2)

        log.info("Compilation DB: {}", os.path.join(outdir, "all_compile_commands.json"))
