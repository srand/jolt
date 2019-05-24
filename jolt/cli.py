import click
import imp
import subprocess
import sys
import webbrowser
from os import _exit

from jolt.tasks import TaskRegistry, Parameter
from jolt import scheduler
from jolt import graph
from jolt import cache
from jolt import filesystem as fs
from jolt import log
from jolt.log import logfile
from jolt import config
from jolt.loader import JoltLoader
from jolt import utils
from jolt.influence import HashInfluenceRegistry, taint
from jolt.options import JoltOptions
from jolt.hooks import TaskHookRegistry
from jolt.manifest import JoltManifest
from jolt.error import JoltError
from jolt.error import raise_error
from jolt.error import raise_error_if
from jolt.error import raise_task_error_if


debug_enabled = False


class ArgRequiredUnless(click.Argument):
    def __init__(self, *args, **kwargs):
        self.required_unless = kwargs.pop('required_unless')
        assert self.required_unless, "'required_unless' parameter required"
        super(ArgRequiredUnless, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.required_unless not in opts:
            if not opts.get(self.name, None):
                self.required = True
        return super(ArgRequiredUnless, self).handle_parse_result(
            ctx, opts, args)


class PluginGroup(click.Group):
    def get_command(self, ctx, cmd_name):

        if ctx.params.get("verbose", False):
            log.set_level(log.VERBOSE)
        if ctx.params.get("extra_verbose", False):
            log.set_level(log.DEBUG)
        if ctx.params.get("config_file"):
            config.load(ctx.params.get("config_file"))

        # Load configured plugins
        imp.new_module("jolt.plugins")
        for section in config.sections():
            path = fs.path.dirname(__file__)
            path = fs.path.join(path, "plugins", section + ".py")
            if fs.path.exists(path):
                imp.load_source("jolt.plugins." + section, path)

        return click.Group.get_command(self, ctx, cmd_name)


@click.group(cls=PluginGroup)
@click.option("-v", "--verbose", is_flag=True, help="Verbose.")
@click.option("-vv", "--extra-verbose", is_flag=True, help="Verbose.")
@click.option("-c", "--config-file", type=str, help="Configuration file")
@click.option("-d", "--debug", is_flag=True, help="Attach debugger on exception", hidden=True)
@click.option("-p", "--profile", is_flag=True, help="Profile code while running", hidden=True)
@click.pass_context
def cli(ctx, verbose, extra_verbose, config_file, debug, profile):
    """ Jolt - a task execution tool. """

    global debug_enabled
    debug_enabled = debug

    manifest = JoltManifest()
    try:
        manifest.parse()
        manifest.process_import()
    except:
        pass
    ctx.obj["manifest"] = manifest

    # Load additional plugins configured through manifest
    for section in config.sections():
        path = fs.path.dirname(__file__)
        path = fs.path.join(path, "plugins", section + ".py")
        if fs.path.exists(path):
            mod = "jolt.plugins." + section
            if mod not in sys.modules:
                imp.load_source(mod, path)

    loader = JoltLoader.get()
    tasks, tests = loader.load()
    for cls in tasks:
        TaskRegistry.get().add_task_class(cls)
    for cls in tests:
        TaskRegistry.get().add_test_class(cls)


def _autocomplete_tasks(ctx, args, incomplete):
    tasks, tests = JoltLoader.get().load()
    tasks = [task.name for task in tasks + tests if task.name.startswith(incomplete or '')]
    return sorted(tasks)


@cli.command()
@click.argument("task", type=str, nargs=-1, autocompletion=_autocomplete_tasks, cls=ArgRequiredUnless, required_unless="worker")
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
@click.option("-f", "--force", is_flag=True, default=False, help="Force rebuild (taint hash).")
@click.option("-c", "--copy", type=click.Path(),
              help="Copy artifact content to this directory upon completion.")
@click.pass_context
def build(ctx, task, network, keep_going, identity, default, local,
          no_download, no_upload, download, upload, worker, force, copy):
    """
    Execute specified task.

    <WIP>
    """
    duration = utils.duration()

    task = list(task)
    task = [utils.stable_task_name(t) for t in task]

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

    TaskHookRegistry.get(options)
    registry = TaskRegistry.get(options)

    for params in default:
        registry.set_default_parameters(params)

    manifest = ctx.obj["manifest"]

    for mb in manifest.builds:
        for mt in mb.tasks:
            task.append(mt.name)
        for mt in mb.defaults:
            registry.set_default_parameters(mt.name)

    gb = graph.GraphBuilder(registry, manifest, progress=True)
    dag = gb.build(task)

    # Inform cache about what task artifacts we will need.
    acache.advise(dag.tasks)

    if identity:
        root = dag.select(lambda graph, task: task.identity.startswith(identity))
        raise_error_if(len(root) < 1, "unknown hash identity, no such task '{0}'", identity)

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
                raise_error_if(not task, "no more tasks in progress, only blocked tasks remain")

            if not keep_going and error is not None:
                queue.abort()
                raise error

        for goal in goal_tasks:
            if acache.is_available_locally(goal):
                with acache.get_artifact(goal) as artifact:
                    log.info("Location: {0}", artifact.path)
                    if copy:
                        artifact.copy("*", click.format_filename(copy))

        log.info("Total execution time: {0} {1}",
                 str(duration),
                 str(queue.duration_acc) if network else '')
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        try:
            queue.abort()
            return
        except KeyboardInterrupt:
            log.warning("Interrupted again, exiting")
            _exit(1)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=_autocomplete_tasks)
@click.option("-d", "--deps", is_flag=True, help="Clean all task dependencies.")
@click.option("-e", "--expired", is_flag=True, help="Only clean expired tasks.")
@click.pass_context
def clean(ctx, task, deps, expired):
    """
    Removes task artifacts and intermediate files.

    When run without arguments, this command removes all task artifacts
    from the local cache, but no intermediate files are removed.

    When a task is specified, the task clean() method is invoked to remove
    any intermediate files still present in persistent build directories.
    Secondly, the task artifact will be removed from the local cache.
    Global caches are not affected. The --deps parameter can be used to also
    clean all dependencies of the specified task.

    By default, task artifacts are removed without considering any
    artifact expiration metadata. To only remove artifact which have expired,
    use the --expired parameter. Artifacts typically expire immediately after
    creation unless explicitly configured not to.
    """
    acache = cache.ArtifactCache.get()
    if task:
        task = [utils.stable_task_name(t) for t in task]
        registry = TaskRegistry.get()
        dag = graph.GraphBuilder(registry, ctx.obj["manifest"]).build(task)
        if deps:
            tasks = dag.tasks
        else:
            tasks = dag.select(
                lambda graph, node: node.short_qualified_name in task or \
                node.qualified_name in task)
        for task in tasks:
            task.clean(acache, expired)
    else:
        acache.discard_all(expired)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=_autocomplete_tasks)
@click.option("-p", "--prune", is_flag=True, help="Omit tasks with cached artifacts.")
@click.pass_context
def display(ctx, task, prune):
    """
    Display a task and its dependencies visually.

    <WIP>
    """
    registry = TaskRegistry.get()
    gb = graph.GraphBuilder(registry, ctx.obj["manifest"])
    dag = gb.build(task, influence=False)
    if prune:
        acache = cache.ArtifactCache.get()
        dag.prune(lambda graph, task: task.is_available_locally(acache) or task.is_resource())
    if dag.has_tasks():
        try:
            gb.display()
        except JoltError as e:
            raise e
        except Exception as e:
            raise_error_if("requires pygraphviz" in str(e), "this features requires pygraphviz, please install it")
            raise_error("an exception occurred during task dependency evaluation, see log for details")
    else:
        log.info("no tasks to display")


@cli.command()
def docs():
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
    scheduler.ExecutorRegistry.get(options)
    registry = TaskRegistry.get()

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, manifest)
    dag = gb.build(task)

    available_in_cache = [
        (t.is_available_locally(acache) or (
            t.is_available_remotely(acache) and acache.download_enabled()), t)
        for t in dag.tasks if t.is_cacheable()]

    for available, task in available_in_cache:
        raise_task_error_if(
            not available, task,
            "task artifact is not available in any cache, build it first")

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
        dag = graph.GraphBuilder(registry, ctx.obj["manifest"]).build(task, influence=False)
    except JoltError as e:
        raise e
    except:
        raise_error("an exception occurred during task dependency evaluation, see log for details")

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
        subprocess.call("tail -f {0}".format(logfile), shell=True)
    elif delete:
        fs.unlink(logfile)
    else:
        subprocess.call("less {0}".format(logfile), shell=True)


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
    task = task_registry.get_task_class(task_cls_name) or \
           task_registry.get_test_class(task_cls_name)
    raise_task_error_if(not task, task_name, "no such task")

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
            string = string.split(":", 1)
            click.echo("    {:<18}{}".format(string[0][10:], string[1].strip()))
