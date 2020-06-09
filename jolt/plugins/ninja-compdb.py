import click
import json
import os
import sys

from jolt import cache
from jolt import cli
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

            # Add information about the workspace root
            with open(tools.expand_path("compile_commands.json")) as f:
                commands = json.load(f)
            for command in commands:
                command["joltdir"] = task.task.joltdir
            with open(tools.expand_path("compile_commands.json"), "w") as f:
                json.dump(commands, f, indent=2)

    def task_postpublish(self, task, artifact, tools):
        if not isinstance(task.task, ninja.CXXProject):
            return

        with tools.cwd(task.task.outdir):
            artifact.collect("*compile_commands.json")


@TaskHookFactory.register
class CompDBHookFactory(TaskHookFactory):
    def create(self, env):
        return CompDBHooks()


@cli.cli.command(name="compdb")
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=cli._autocomplete_tasks)
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.pass_context
def compdb(ctx, task, default):
    """ Generate a compilation database for the specified task. """

    manifest = ctx.obj["manifest"]
    options = JoltOptions(default=default)
    acache = cache.ArtifactCache.get(options)
    hooks = TaskHookRegistry.get(options)
    executors = scheduler.ExecutorRegistry.get(options)
    registry = TaskRegistry.get()
    strategy = scheduler.DownloadStrategy(executors, acache)
    queue = scheduler.TaskQueue(strategy)

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, manifest, options, progress=True)
    dag = gb.build(task)

    available_in_cache = [
        (t.is_available_locally(acache) or (
            t.is_available_remotely(acache) and acache.download_enabled()), t)
        for t in dag.tasks if t.is_cacheable()]

    for available, task in available_in_cache:
        raise_task_error_if(
            not available, task,
            "task artifact is not available in any cache, build it first")

    for goal in dag.goals:
        raise_task_error_if(
            not isinstance(goal.task, ninja.CXXProject),
            "not a Ninja C++ task")

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
            outdir = goal.tools.builddir("ninja", True)

            # Load commands from goal task
            artifact = acache.get_artifact(goal)
            with goal.tools.cwd(artifact.path):
                with open(goal.tools.expand_path("compile_commands.json")) as f:
                    all_commands = json.load(f)

            # Load commands from goal task dependencies
            for name, artifact in context.items():
                try:
                    with goal.tools.cwd(artifact.path):
                        with open(goal.tools.expand_path("compile_commands.json")) as f:
                            commands = json.load(f)
                    all_commands.extend(commands)
                    goal.tools.sandbox(artifact, incremental=True, reflect=True)
                except Exception:
                    pass

            # Patch commands to use reflected sandboxes
            for command in all_commands:
                command["command"] = command["command"].replace(
                    "sandbox-", "sandbox-reflect-")
                try:
                    command["directory"] = command["directory"].replace(
                        command["joltdir"], artifact.get_task().joltdir)
                except Exception:
                    pass

            # Write result
            with goal.tools.cwd(outdir):
                with open(goal.tools.expand_path("all_compile_commands.json"), "w") as f:
                    json.dump(all_commands, f, indent=2)

        log.info("Compilation DB: {}/all_compile_commands.json", outdir)
