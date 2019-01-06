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
from jolt import loader
from jolt import utils
from jolt.influence import *


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Verbose.")
@click.option("-vv", "--extra-verbose", is_flag=True, help="Verbose.")
@click.option("-c", "--config-file", type=str, help="Configuration file")
def cli(verbose, extra_verbose, config_file):
    """ Jolt - a task execution tool. """

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

    tasks, tests = loader.JoltLoader().get().load()
    for cls in tasks:
        TaskRegistry.get().add_task_class(cls)
    for cls in tests:
        TaskRegistry.get().add_test_class(cls)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=True)
@click.option("-n", "--network", is_flag=True, default=False, help="Build on network.")
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
def build(task, network, keep_going, identity, no_download, no_upload, download, upload):
    """
    Execute specified task.

    <WIP>
    """

    if no_download:
        config.set("jolt", "download", "false")
    if no_upload:
        config.set("jolt", "upload", "false")
    if download:
        config.set("jolt", "download", "true")
    if upload:
        config.set("jolt", "upload", "true")

    executor = scheduler.ExecutorRegistry.get(network=network)
    acache = cache.ArtifactCache()
    registry = TaskRegistry().get()
    gb = graph.GraphBuilder(registry)
    dag = gb.build(task)
    dag.prune(lambda graph, task: task.is_cached(acache, network))

    if identity:
        root = dag.select(lambda graph, task: task.identity.startswith(identity))
        assert len(root) >= 1, "unknown hash identity, no such task: {0}".format(identity)

    queue = scheduler.TaskQueue(executor)

    def signal_handle(_signal, frame):
        print('You pressed Ctrl+C!')
        queue.abort()
    signal.signal(signal.SIGINT, signal_handle)

    while dag.nodes:
        leafs = dag.select(lambda graph, task: task.is_ready())
        while leafs:
            task = leafs.pop()
            task.set_in_progress()
            queue.submit(acache, task)

        task, error = queue.wait()
        if not task:
            dag.debug()
            assert task, "no more tasks in progress, only blocked tasks remain"

        if not keep_going and error is not None:
            queue.abort()
            raise error


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False)
def clean(task):
    """
    Remove (task artifact from) local cache.

    <WIP>
    """
    acache = cache.ArtifactCache()
    if task:
        registry = TaskRegistry().get()
        dag = graph.GraphBuilder(registry).build(task)
        tasks = dag.select(lambda graph, node: node.name in task)
        for task in tasks:
            acache.discard(task)
    else:
        fs.rmtree(acache.root)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False)
@click.option("-p", "--prune", is_flag=True, help="Omit tasks with cached artifacts.")
def display(task, prune):
    """
    Display a task and its dependencies visually.

    <WIP>
    """
    registry = TaskRegistry.get()
    gb = graph.GraphBuilder(registry)
    dag = gb.build(task)
    if prune:
        acache = cache.ArtifactCache()
        dag.prune(lambda graph, task: task.is_cached(acache, network=False))
    if len(dag.nodes) > 0:
        gb.display()
    else:
        log.info("No tasks to display")


@cli.command()
@click.option("-f", "--follow", is_flag=True, help="Display log output as it appears")
@click.option("-D", "--delete", is_flag=True, help="Delete the log file")
def docs(follow, delete):
    """
    Opens the Jolt documentation in the default webbrowser.
    """
    webbrowser.open("http://jolt.readthedocs.io/")


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False)
@click.option("-a", "--all", is_flag=True, help="Print all tasks recursively")
def list(task=None, reverse=False, all=False):
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

    dag = graph.GraphBuilder(registry).build(task)
    tasks = dag.select(lambda graph, node: node.short_qualified_name in task)
    successors = set()
    for task in tasks:
        map(successors.add, dag.successors(task))

    for task in sorted(successors):
        print(task.qualified_name)


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
@click.argument("task")
@click.option("-i", "--influence", is_flag=True, help="Print task influence.")
def info(task, influence=False):
    """
    View information about a task, including its documentation.

    <WIP>
    """
    task_registry = TaskRegistry.get()
    task = task_registry.get_task(task)

    click.echo()
    click.echo("  {0}".format(task.name))
    click.echo()
    if task.__doc__:
        click.echo("  {0}".format(task.__doc__.strip()))
        click.echo()
    click.echo("  Parameters")
    has_param = False
    for item, param in task.__dict__.items():
        if isinstance(param, Parameter):
            has_param = True
            click.echo("    {0:<15}   {1}".format(item, param.__doc__ or ""))
    if not has_param:
        click.echo("    None")

    click.echo()
    click.echo("  Requirements")
    for req in task.requires:
        click.echo("    {0}".format(req))
    if not task.requires:
        click.echo("    None")
    click.echo()

    acache = cache.ArtifactCache()
    dag = graph.GraphBuilder(task_registry).build(
        [utils.format_task_name(task.name, task._get_parameters())])
    tasks = dag.select(lambda graph, node: graph.is_root(node))
    assert len(tasks) == 1, "unexpected graph generated"
    proxy = tasks[0]

    click.echo("  Cache")
    click.echo("    Identity          {0}".format(proxy.identity))
    if acache.is_available_locally(proxy):
        click.echo("    Local             {0} ({1})".format(
            True, utils.as_human_size(acache.get_artifact(proxy).get_size())))
    click.echo("    Remote            {0}".format(acache.is_available_remotely(proxy)))
    click.echo()

    if influence:
        click.echo("  Influence")
        for string in HashInfluenceRegistry.get().get_strings(task):
            click.echo("    " + string)
        click.echo()
