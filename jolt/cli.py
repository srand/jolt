import click
import imp
import traceback
import subprocess
import signal
import sys
import webbrowser


from jolt.tasks import Task, TaskRegistry, Parameter
from jolt import scheduler
from jolt import graph
from jolt import cache
from jolt import filesystem as fs
from jolt import log
from jolt.log import path as log_path
from jolt import config
from jolt import plugins
from jolt.plugins import cxxinfo, environ, strings
from jolt.loader import JoltLoader
from jolt import utils
from jolt.influence import *
from jolt.options import JoltOptions
from jolt.hooks import TaskHookRegistry
from jolt.manifest import JoltManifest

debug_enabled = False


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Verbose.")
@click.option("-vv", "--extra-verbose", is_flag=True, help="Verbose.")
@click.option("-c", "--config-file", type=str, help="Configuration file")
@click.option("-d", "--debug", is_flag=True, help="Attach debugger on exception", hidden=True)
@click.pass_context
def cli(ctx, verbose, extra_verbose, config_file, debug):
    """ Jolt - a task execution tool. """

    global debug_enabled
    debug_enabled = debug

    if verbose:
        log.set_level(log.VERBOSE)
    if extra_verbose:
        log.set_level(log.HYSTERICAL)
    if config_file:
        config.load(config_file)

    # Load configured plugins
    for section in config.sections():
        path = fs.path.dirname(__file__)
        path = fs.path.join(path, "plugins", section + ".py")
        if fs.path.exists(path):
            imp.load_source("jolt.plugins." + section, path)

    manifest = JoltManifest()
    try:
        manifest.parse()
    except:
        pass
    ctx.obj["manifest"] = manifest

    loader = JoltLoader.get()
    tasks, tests = loader.load(manifest)
    for cls in tasks:
        TaskRegistry.get().add_task_class(cls)
    for cls in tests:
        TaskRegistry.get().add_test_class(cls)


def _autocomplete_tasks(ctx, args, incomplete):
    tasks, tests = loader.JoltLoader.get().load()
    tasks = [task.name for task in tasks + tests if task.name.startswith(incomplete or '')]
    return sorted(tasks)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=True, autocompletion=_autocomplete_tasks)
@click.option("-n", "--network", is_flag=True, default=False, help="Build on network.")
@click.option("-l", "--local", is_flag=True, default=False, help="Disable all network operations.")
@click.option("-k", "--keep-going", is_flag=True, default=False, help="Build as many tasks as possible, don't abort on first failure.")
@click.option("-i", "--identity", type=str, help="Expected hash identity")
@click.option("--no-download", is_flag=True, default=False,
              help="Don't download artifacts from remote storage")
@click.option("--no-upload", is_flag=True, default=False,
              help="Don't upload artifacts to remote storage")
@click.option("--download", is_flag=True, default=False,
              help="Do download artifacts from remote storage")
@click.option("--upload", is_flag=True, default=False,
              help="Do upload artifacts to remote storage")
@click.option("--worker", is_flag=True, default=False,
              help="Run with the worker build strategy", hidden=True)
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.option("-f", "--force", is_flag=True, default=False, help="Force rebuild.")
@click.pass_context
def build(ctx, task, network, keep_going, identity, default, local,
          no_download, no_upload, download, upload, worker, force):
    """
    Execute specified task.

    <WIP>
    """
    duration = utils.duration()

    if network:
        _download = config.getboolean("network", "download", True)
        _upload = config.getboolean("network", "upload", True)
    else:
        _download = config.getboolean("jolt", "download", True)
        _upload = config.getboolean("jolt", "upload", True)

    if local:
        _download = False
        _upload = False
    else:
        if no_download:
            _download = False
        if no_upload:
            _upload = False
        if download:
            _download = True
        if upload:
            _upload = True

    if force:
        taint()

    options = JoltOptions(network=network,
                          local=local,
                          download=_download,
                          upload=_upload,
                          keep_going=keep_going,
                          default=default,
                          worker=worker)

    acache = cache.ArtifactCache.get(options)

    executors = scheduler.ExecutorRegistry.get(options)
    if worker:
        log.verbose("Local build as a worker")
        strategy = scheduler.WorkerStrategy(executors, acache)
    elif network:
        log.verbose("Distributed build as a user")
        strategy = scheduler.DistributedStrategy(executors, acache)
    else:
        log.verbose("Local build as a user")
        strategy = scheduler.LocalStrategy(executors, acache)

    hooks = TaskHookRegistry.get(options)
    registry = TaskRegistry.get(options)

    for params in default:
        registry.set_default_parameters(params)

    manifest = ctx.obj["manifest"]

    gb = graph.GraphBuilder(registry, manifest)
    dag = gb.build(task)

    # Inform cache about what task artifacts we will need.
    acache.advise(dag.tasks)

    if identity:
        root = dag.select(lambda graph, task: task.identity.startswith(identity))
        assert len(root) >= 1, "unknown hash identity, no such task: {0}".format(identity)

    goal_tasks = dag.select(
        lambda graph, node: node.short_qualified_name in task or \
        node.qualified_name in task)

    queue = scheduler.TaskQueue(strategy)

    try:
        if not dag.has_tasks():
            return

        while dag.has_tasks():
            leafs = dag.select(lambda graph, task: task.is_ready())
            while leafs:
                task = leafs.pop()
                queue.submit(acache, task)

            task, error = queue.wait()
            if not task:
                dag.debug()
                assert task, "no more tasks in progress, only blocked tasks remain"

            if not keep_going and error is not None:
                queue.abort()
                raise error

        for goal in goal_tasks:
            if acache.is_available_locally(goal):
                with acache.get_artifact(goal) as artifact:
                    log.info("Location: {0}", artifact.path)

        log.info("Total execution time: {0} {1}",
                 str(duration),
                 str(queue.duration_acc) if network else '')
    except KeyboardInterrupt:
        log.warn("Interrupted by user")
        try:
            queue.abort()
            return
        except KeyboardInterrupt:
            log.warn("Interrupted again, exiting")
            os._exit(1)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=_autocomplete_tasks)
@click.pass_context
def clean(ctx, task):
    """
    Remove (task artifact from) local cache.

    <WIP>
    """
    acache = cache.ArtifactCache.get()
    if task:
        task = [utils.stable_task_name(t) for t in task]
        registry = TaskRegistry.get()
        dag = graph.GraphBuilder(registry, ctx.obj["manifest"]).build(task)
        tasks = dag.select(
            lambda graph, node: node.short_qualified_name in task or \
            node.qualified_name in task)
        for task in tasks:
            acache.discard(task)
    else:
        fs.rmtree(acache.root)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=_autocomplete_tasks)
@click.option("-p", "--prune", is_flag=True, help="Omit tasks with cached artifacts.")
@click.pass_context
def display(ctx, task, prune):
    """
    Display a task and its dependencies visually.

    <WIP>
    """
    options = JoltOptions()
    registry = TaskRegistry.get()
    gb = graph.GraphBuilder(registry, ctx.obj["manifest"])
    dag = gb.build(task)
    if prune:
        acache = cache.ArtifactCache.get()
        dag.prune(lambda graph, task: task.is_available_locally(acache) or task.is_resource())
    if dag.has_tasks():
        try:
            gb.display()
        except Exception as e:
            if "requires pygraphviz" in str(e):
                assert False, "this features requires pygraphviz, please install it"
            assert False, "an exception occurred during task dependency evaluation, see log for details"
    else:
        log.info("no tasks to display")


@cli.command()
@click.option("-f", "--follow", is_flag=True, help="Display log output as it appears")
@click.option("-D", "--delete", is_flag=True, help="Delete the log file")
def docs(follow, delete):
    """
    Opens the Jolt documentation in the default webbrowser.
    """
    webbrowser.open(config.get("jolt", "docs", "http://jolt.readthedocs.io/"))


@cli.command(hidden=True)
@click.argument("task", type=str, nargs=-1, required=True)
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.option("-o", "--output", type=str, default="default.joltxmanifest", help="Manifest filename.")
@click.pass_context
def freeze(ctx, task, default, output):
    """
    Freeze the identity of a task.

    <WIP>
    """
    manifest = ctx.obj["manifest"]

    options = JoltOptions(default=default)
    acache = cache.ArtifactCache.get(options)
    executors = scheduler.ExecutorRegistry.get(options)
    registry = TaskRegistry.get()

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, manifest)
    dag = gb.build(task)

    available_in_cache = [
        (t.is_available_locally(acache) or t.is_available_remotely(acache), t.name)
        for t in dag.tasks if t.is_cacheable()]
    assert all(available_in_cache),\
        "can't freeze '{0}': not available in any cache, build it first"\
        .format(" ".join(task))

    for task in dag.tasks:
        if not manifest.has_task(task):
            manifest_task = manifest.create_task()
            manifest_task.name = task.qualified_name
            manifest_task.identity = task.identity

    manifest.write(fs.path.join(JoltLoader.get().joltdir, output))


@cli.command(name="list")
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=_autocomplete_tasks)
@click.pass_context
def _list(ctx, task=None, reverse=False):
    """
    List all tasks, or dependencies of a specific task.

    <WIP>
    """

    registry = TaskRegistry.get()

    if not task:
        classes = registry.get_task_classes()
        classes += registry.get_test_classes()
        for task in sorted(classes, key=lambda x: x.name):
            if task.name:
                print(task.name)
        return

    task = [utils.stable_task_name(t) for t in task]

    try:
        dag = graph.GraphBuilder(registry, ctx.obj["manifest"]).build(task)
    except:
        assert False, "an exception occurred during task dependency evaluation, see log for details"

    tasks = dag.select(lambda graph, node: \
                       node.short_qualified_name in task or \
                       node.qualified_name in task)
    successors = set()
    for task in tasks:
        for successor in dag.successors(task):
            successors.add(successor.short_qualified_name)

    for task in sorted(list(successors)):
        print(task)


@cli.command(name="log")
@click.option("-f", "--follow", is_flag=True, help="Display log output as it appears")
@click.option("-D", "--delete", is_flag=True, help="Delete the log file")
def _log(follow, delete):
    """
    Access the Jolt log file.

    <WIP>
    """
    if follow:
        subprocess.call("tail -f {0}".format(log_path), shell=True)
    elif delete:
        fs.unlink(log_path)
    else:
        subprocess.call("less {0}".format(log_path), shell=True)


@cli.command()
@click.argument("task", autocompletion=_autocomplete_tasks)
@click.option("-i", "--influence", is_flag=True, help="Print task influence.")
@click.option("-a", "--artifacts", is_flag=True, help="Print task artifact status.")
@click.pass_context
def info(ctx, task, influence=False, artifacts=False):
    """
    View information about a task, including its documentation.

    <WIP>
    """
    task_name = task
    task_cls_name, task_params = utils.parse_task_name(task_name)
    task_registry = TaskRegistry.get()
    task = task_registry.get_task_class(task_cls_name)
    assert task, "no such task: {0}".format(task_name)

    click.echo()
    click.echo("  {0}".format(task.name))
    click.echo()
    if task.__doc__:
        click.echo("  {0}".format(task.__doc__.strip()))
        click.echo()
    click.echo("  Parameters")
    has_param = False
    params = { key: getattr(task, key) for key in dir(task)
               if isinstance(utils.getattr_safe(task, key), Parameter) }
    for item, param in params.items():
        has_param = True
        click.echo("    {0:<15}   {1}".format(item, param.__doc__ or ""))
    if not has_param:
        click.echo("    None")

    click.echo()
    click.echo("  Requirements")
    try:
        task = task_registry.get_task(task_name)
        for req in utils.as_list(utils.call_or_return(task, task.requires)):
            click.echo("    {0}".format(task.tools.expand(req)))
        if not task.requires:
            click.echo("    None")
        click.echo()
    except Exception as e:
        log.exception()
        if "has not been set" in str(e):
            click.echo("    Unavailable (parameters must be set)")
            click.echo()
            return
        click.echo("    Unavailable (exception during evaluation)")
        click.echo()
        return


    if artifacts:
        acache = cache.ArtifactCache.get()
        dag = graph.GraphBuilder(task_registry, ctx.obj["manifest"]).build(
            [utils.format_task_name(task.name, task._get_parameters())])
        tasks = dag.select(lambda graph, node: graph.is_root(node))
        assert len(tasks) == 1, "unexpected graph generated"
        proxy = tasks[0]

        click.echo("  Cache")
        click.echo("    Identity          {0}".format(proxy.identity))
        if acache.is_available_locally(proxy):
            with acache.get_artifact(proxy) as artifact:
                click.echo("    Location          {0}".format(artifact.path))
            click.echo("    Local             {0} ({1})".format(
                True, utils.as_human_size(acache.get_artifact(proxy).get_size())))
            click.echo("    Remote            {0}".format(acache.is_available_remotely(proxy)))
            click.echo()

        if influence:
            click.echo("  Influence")
            for string in HashInfluenceRegistry.get().get_strings(task):
                click.echo("    " + string)
                click.echo()
