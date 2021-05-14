import click
import imp
import subprocess
import sys
import uuid
import webbrowser
from os import _exit, environ, getcwd

from jolt.tasks import TaskRegistry, Parameter
from jolt import scheduler
from jolt import graph
from jolt import cache
from jolt import colors
from jolt import filesystem as fs
from jolt import log
from jolt.log import logfile
from jolt import config
from jolt.loader import JoltLoader
from jolt import tools
from jolt import utils
from jolt.influence import HashInfluenceRegistry
from jolt.options import JoltOptions
from jolt import hooks
from jolt.manifest import JoltManifest
from jolt.error import JoltError
from jolt.error import raise_error
from jolt.error import raise_error_if
from jolt.error import raise_task_error_if
from jolt.plugins import report

debug_enabled = False
workdir = getcwd()


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
        config_files = ctx.params.get("config_file") or []
        for config_file in config_files:
            log.verbose("Config: {0}", config_file)
            config.load_or_set(config_file)

        # Load configured plugins
        JoltLoader.get().load_plugins()

        return click.Group.get_command(self, ctx, cmd_name)


@click.group(cls=PluginGroup, invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Verbose output.")
@click.option("-vv", "--extra-verbose", is_flag=True, help="Extra verbose output.")
@click.option("-c", "--config", "config_file", multiple=True, type=str,
              help="Load a configuration file or set a configuration key.")
@click.option("-d", "--debug-exception", is_flag=True, hidden=True,
              help="Attach debugger on exception")
@click.option("-p", "--profile", is_flag=True, hidden=True,
              help="Profile code while running")
@click.option("-f", "--force", is_flag=True, default=False, hidden=True,
              help="Force rebuild of target tasks.")
@click.option("-s", "--salt", type=str, hidden=True,
              help="Add salt as task influence.")
@click.option("-g", "--debug", is_flag=True, default=False, hidden=True,
              help="Start debug shell before executing task.")
@click.option("-n", "--network", is_flag=True, default=False, hidden=True,
              help="Build on network.")
@click.option("-l", "--local", is_flag=True, default=False, hidden=True,
              help="Disable all network operations.")
@click.option("-k", "--keep-going", is_flag=True, default=False, hidden=True,
              help="Build as many tasks as possible, don't abort on first failure.")
@click.option("-j", "--jobs", type=int, default=1, hidden=True,
              help="Number of tasks allowed to execute in parallel (1). ")
@click.pass_context
def cli(ctx, verbose, extra_verbose, config_file, debug_exception, profile,
        force, salt, debug, network, local, keep_going, jobs):
    """
    Jolt - a task execution tool.

    When invoked without any commands and arguments, Jolt by default tries
    to execute and build the artifact of a task called `default`. If the
    default task doesn't exist this help text is printed. All other tasks
    can be executed with the build command. Note that most build command
    options can be used also when executing the default task without
    specifying a command. See the build command help for details.

    To execute the default task and its dependencies without stopping on
    failures, run:

      $ jolt -k

    """

    global debug_enabled
    debug_enabled = debug_exception

    log.verbose("Jolt host: {}", environ.get("HOSTNAME", "localhost"))
    log.verbose("Jolt install path: {}", fs.path.dirname(__file__))

    if ctx.invoked_subcommand in ["config"]:
        # Don't attempt to load any task recipes as they might require
        # plugins that are not yet configured.
        return

    if ctx.invoked_subcommand is None:
        build = ctx.command.get_command(ctx, "build")

    manifest = JoltManifest()
    utils.call_and_catch(manifest.parse)
    manifest.process_import()
    ctx.obj["manifest"] = manifest

    loader = JoltLoader.get()
    tasks = loader.load()
    for cls in tasks:
        TaskRegistry.get().add_task_class(cls)

    if ctx.invoked_subcommand in ["build", "clean"] and loader.joltdir:
        ctx.obj["workspace_lock"] = utils.LockFile(
            fs.path.join(loader.joltdir, "build"),
            log.info, "Workspace is locked by another process, please wait...")

    # If no command is given, we default to building the default task.
    # If the default task doesn't exist, help is printed inside build().
    if ctx.invoked_subcommand is None:
        task = config.get("jolt", "default", "default")
        taskname, _ = utils.parse_task_name(task)
        if TaskRegistry.get().get_task_class(taskname) is not None:
            ctx.invoke(build, task=[task], force=force, salt=salt, debug=debug,
                       network=network, local=local, keep_going=keep_going, jobs=jobs)
        else:
            print(cli.get_help(ctx))
            sys.exit(1)


def _autocomplete_tasks(ctx, args, incomplete):
    manifest = JoltManifest()
    utils.call_and_catch(manifest.parse)
    manifest.process_import()

    tasks = JoltLoader.get().load()
    tasks = [task.name for task in tasks if task.name.startswith(incomplete or '')]
    return sorted(tasks)


@cli.command()
@click.argument("task", type=str, nargs=-1, autocompletion=_autocomplete_tasks, cls=ArgRequiredUnless, required_unless="worker")
@click.option("-n", "--network", is_flag=True, default=False, help="Build on network.")
@click.option("-l", "--local", is_flag=True, default=False, help="Disable all network operations.")
@click.option("-k", "--keep-going", is_flag=True, default=False, help="Build as many tasks as possible, don't abort on first failure.")
@click.option("-i", "--identity", type=str, help="Expected hash identity")
@click.option("-j", "--jobs", type=int, default=1, help="Number of tasks allowed to execute in parallel (1). ")
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
@click.option("-f", "--force", is_flag=True, default=False, help="Force rebuild of target tasks.")
@click.option("-s", "--salt", type=str, help="Add salt as task influence.")
@click.option("-g", "--debug", is_flag=True, default=False,
              help="Start debug shell before executing task.")
@click.option("-c", "--copy", type=click.Path(),
              help="Copy artifact content to this directory upon completion.")
@click.option("--result", type=click.Path(), hidden=True,
              help="Write result manifest to this file.")
@click.pass_context
@hooks.cli_build
def build(ctx, task, network, keep_going, identity, default, local,
          no_download, no_upload, download, upload, worker, force,
          salt, copy, debug, result, jobs):
    """
    Execute a specific task.

    """
    raise_error_if(network and local,
                   "The -n and -l flags are mutually exclusive")

    raise_error_if(network and debug,
                   "The -g and -n flags are mutually exclusive")

    raise_error_if(no_download and download,
                   "The --download and --no-download flags are mutually exclusive")

    raise_error_if(no_upload and upload,
                   "The --upload and --no-upload flags are mutually exclusive")

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

    options = JoltOptions(network=network,
                          local=local,
                          download=_download,
                          upload=_upload,
                          keep_going=keep_going,
                          default=default,
                          worker=worker,
                          debug=debug,
                          salt=salt,
                          jobs=jobs)

    acache = cache.ArtifactCache.get(options)

    executors = scheduler.ExecutorRegistry.get(options)
    if worker:
        log.set_worker()
        log.verbose("Local build as a worker")
        strategy = scheduler.WorkerStrategy(executors, acache)
    elif network:
        log.verbose("Distributed build as a user")
        strategy = scheduler.DistributedStrategy(executors, acache)
    else:
        log.verbose("Local build as a user")
        strategy = scheduler.LocalStrategy(executors, acache)

    hooks.TaskHookRegistry.get(options)
    registry = TaskRegistry.get(options)

    for params in default:
        registry.set_default_parameters(params)

    manifest = ctx.obj["manifest"]

    for mb in manifest.builds:
        for mt in mb.tasks:
            task.append(mt.name)
        for mt in mb.defaults:
            registry.set_default_parameters(mt.name)

    if force:
        for goal in task:
            registry.get_task(goal, manifest=manifest).taint = uuid.uuid4()

    gb = graph.GraphBuilder(registry, manifest, options, progress=True)
    dag = gb.build(task)

    gp = graph.GraphPruner(strategy)
    dag = gp.prune(dag)

    goal_tasks = dag.goals
    goal_task_duration = 0

    queue = scheduler.TaskQueue(strategy)

    try:
        if not dag.has_tasks():
            return

        progress = log.progress(
            "Progress",
            dag.number_of_tasks(filterfn=lambda t: not t.is_resource()),
            " tasks",
            estimates=False,
            debug=debug)

        with progress:
            while dag.has_tasks():
                # Find all tasks ready to be executed
                leafs = dag.select(lambda graph, task: task.is_ready())

                # Order the tasks by their weights to improve build times
                leafs.sort(key=lambda x: x.weight)

                while leafs:
                    task = leafs.pop()
                    queue.submit(acache, task)

                task, error = queue.wait()

                if not task:
                    dag.debug()
                    break
                elif task.is_goal() and task.duration_running:
                    goal_task_duration += task.duration_running.seconds

                if not task.is_resource():
                    progress.update(1)

                if not keep_going and error is not None:
                    queue.abort()
                    raise error

        if dag.failed:
            log.error("List of failed tasks")
            for failed in dag.failed:
                log.error("- {}", failed.log_name.strip("()"))
            raise_error("no more tasks could be executed")

        for goal in goal_tasks:
            if acache.is_available_locally(goal):
                with acache.get_artifact(goal) as artifact:
                    log.info("Location: {0}", artifact.path)
                    if copy:
                        artifact.copy("*", fs.path.join(workdir, click.format_filename(copy)))
    except KeyboardInterrupt:
        print()
        log.warning("Interrupted by user")
        try:
            queue.abort()
            sys.exit(1)
        except KeyboardInterrupt:
            print()
            log.warning("Interrupted again, exiting")
            _exit(1)
    finally:
        log.info("Total execution time: {0} {1}",
                 str(duration),
                 str(queue.duration_acc) if network else '')
        if result:
            with report.update() as manifest:
                manifest.duration = str(goal_task_duration)
                manifest.write(result)


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
            tasks = dag.goals
        for task in tasks:
            task.clean(acache, expired)
    else:
        acache.discard_all(expired)


@cli.command(name="config")
@click.option("-l", "--list", is_flag=True,
              help="List all configuration keys and values.")
@click.option("-d", "--delete", is_flag=True,
              help="Delete configuration key.")
@click.option("-g", "--global", "global_", is_flag=True,
              help="List, set or get configuration keys in the global config.")
@click.option("-u", "--user", is_flag=True,
              help="List, set or get configuration keys in the user config.")
@click.argument("key", type=str, nargs=1, required=False)
@click.argument("value", type=str, nargs=1, required=False)
@click.pass_context
def _config(ctx, list, delete, global_, user, key, value):
    """
    Configure Jolt.

    You can query/set/replace/unset configuration keys with this command.
    Key strings are constructed from the configuration section and the
    option separated by a dot.

    There are tree different configuration sources:

       - A global configuration file

       - A user configuration file

       - Temporary configuration passed on the command line.

    When reading, the values are read from all configuration sources.
    The options --global and --user can be used to tell the command to read
    from only one of the sources. If a configuration key is available from
    multiple sources, temporary CLI configuration has priority followed by
    the user configuration file and lastly the global configuration file.

    When writing, the new values are written to the user configuration by default.
    The options --global and --user can be used to tell the command to write
    to only one of the sources.

    When removing keys, the values are removed from all sources.
    The options --global and --user can be used to restrict removal to one of
    the sources.

    To assign a value to a key:

      $ jolt config jolt.default all   # Change name of the default task

    To list existing keys:

      $ jolt config -l                 # List all existing keys

      $ jolt config -l -g              # List keys in the global config file

      $ jolt config jolt.colors        # Display the value of a key.

    To delete an existing key:

      $ jolt config -d jolt.colors

    To pass temporary configuration:

      $ jolt -c jolt.colors=true config -l

    """

    if delete and not key:
        raise click.UsageError("--delete requires KEY")

    if not key and not list and not key:
        print(ctx.get_help())
        sys.exit(1)

    if global_ and user:
        raise click.UsageError("--global and --user are mutually exclusive")

    alias = None

    if global_:
        alias = "global"
    if user:
        alias = "user"

    def _print_key(section, opt):
        value = config.get(section, opt, alias=alias)
        raise_error_if(value is None, "no such key: {}".format(key))
        print("{} = {}".format(key, value))

    if list:
        for section, option, value in config.items(alias):
            if option:
                print("{}.{} = {}".format(section, option, value))
            else:
                print(section)
    elif delete:
        raise_error_if(config.delete(key, alias) <= 0,
                       "no such key: {}", key)
        config.save()
    elif key:
        section, opt = config.split(key)
        if value:
            raise_error_if(opt is None, "invalid configuration key: {}".format(key))
            config.set(section, opt, value, alias)
            try:
                config.save()
            except Exception as e:
                log.exception()
                raise_error("failed to write configuration file: {}".format(e))
        else:
            if opt:
                _print_key(section, opt)
            else:
                _print_section(section)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=_autocomplete_tasks)
@click.option("-r", "--reverse", type=str, help="Display consumers of REVERSE if TASK is executed.")
@click.option("-c", "--cached", "show_cache", is_flag=True, help="Highlight cache presence with colors.")
@click.pass_context
def display(ctx, task, reverse=None, show_cache=False):
    """
    Display a task and its dependencies visually.

    """
    registry = TaskRegistry.get()
    gb = graph.GraphBuilder(registry, ctx.obj["manifest"])
    dag = gb.build(task, influence=show_cache)

    options = JoltOptions()
    acache = cache.ArtifactCache.get(options)


    if reverse:
        iterator = lambda task: list(dag.predecessors(task))
        reverse = utils.as_list(reverse)
        tasklist = dag.select(lambda graph, node: \
                             node.short_qualified_name in reverse or \
                             node.qualified_name in reverse)
    else:
        tasklist = dag.requested_goals
        iterator = lambda task: task.children


    if dag.has_tasks():
        def _display(task, indent=0, last=None):
            header = ""
            if indent > 0:
                for pipe in last[:-1]:
                    if pipe:
                        header += "\u2502 "
                    else:
                        header += "  "
                if last[-1]:
                    header += "\u251c\u2574"
                else:
                    header += "\u2514\u2574"

            if not show_cache:
                colorize = str
            elif task.is_cacheable() and not acache.is_available(task):
                colorize = colors.red
            else:
                colorize = colors.green

            print(header + colorize(task.short_qualified_name))
            children = iterator(task)
            for i in range(0, len(children)):
                _display(children[i], indent+1, last=(last or []) +[i+1!=len(children)])
        for task in tasklist:
            _display(task)
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
@click.option("-r", "--remove", is_flag=True, help="Remove tasks from existing manifest.")
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.option("-o", "--output", type=str, default="default.joltxmanifest", help="Manifest filename.")
@click.pass_context
def freeze(ctx, task, default, output, remove):
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
            not remove and not available, task,
            "task artifact is not available in any cache, build it first")

    for task in dag.tasks:
        if task.is_resource() or not task.is_cacheable():
            continue
        manifest_task = manifest.find_task(task)
        if remove and manifest_task:
            manifest.remove_task(manifest_task)
            continue
        if not remove:
            if not manifest_task:
                manifest_task = manifest.create_task()
            manifest_task.name = task.qualified_name
            manifest_task.identity = task.identity

    manifest.write(fs.path.join(JoltLoader.get().joltdir, output))


@cli.command(name="list")
@click.argument("task", type=str, nargs=-1, required=False, autocompletion=_autocomplete_tasks)
@click.option("-r", "--reverse", type=str, help="List consumers of REVERSE if TASK is executed.")
@click.pass_context
def _list(ctx, task=None, reverse=None):
    """
    List all tasks, or dependencies of a specific task.

    <WIP>
    """

    raise_error_if(not task and reverse, "TASK required with --reverse")

    registry = TaskRegistry.get()

    if not task:
        classes = registry.get_task_classes()
        classes += registry.get_test_classes()
        for task in sorted(classes, key=lambda x: x.name):
            if task.name:
                print(task.name)
        return

    task = [utils.stable_task_name(t) for t in task]
    reverse = [utils.stable_task_name(t) for t in utils.as_list(reverse or [])]

    try:
        dag = graph.GraphBuilder(registry, ctx.obj["manifest"]).build(task, influence=False)
    except JoltError as e:
        raise e
    except:
        raise_error("an exception occurred during task dependency evaluation, see log for details")

    task = reverse or task
    nodes = dag.select(lambda graph, node: \
                       node.short_qualified_name in task or \
                       node.qualified_name in task)

    tasklist = set()
    iterator = dag.predecessors if reverse else dag.successors

    for node in nodes:
        for task in iterator(node):
            tasklist.add(task.short_qualified_name)

    for task in sorted(list(tasklist)):
        print(task)


@cli.command(name="log")
@click.option("-f", "--follow", is_flag=True, help="Display log output as it appears")
@click.option("-d", "--delete", is_flag=True, help="Delete the log file")
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
        t = tools.Tools()
        configured_pager = config.get("jolt", "pager", environ.get("PAGER", None))
        for pager in [configured_pager, "less", "more", "cat"]:
            if pager and t.which(pager):
                return subprocess.call("{1} {0}".format(logfile, pager), shell=True)
        print(t.read_file(logfile))

@cli.command()
@click.argument("task", autocompletion=_autocomplete_tasks)
@click.option("-i", "--influence", is_flag=True, help="Print task influence.")
@click.option("-a", "--artifacts", is_flag=True, help="Print task artifact status.")
@click.option("-s", "--salt", type=str, help="Add salt as task influence.")
@click.pass_context
def info(ctx, task, influence=False, artifacts=False, salt=None):
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
    manifest = ctx.obj["manifest"]
    try:
        task = task_registry.get_task(task_name, manifest=manifest)
        for req in sorted(utils.as_list(utils.call_or_return(task, task.requires))):
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

    if salt:
        task.taint = salt

    if artifacts:
        acache = cache.ArtifactCache.get()
        builder = graph.GraphBuilder(task_registry, manifest)
        dag = builder.build([task.qualified_name])
        tasks = dag.select(lambda graph, node: node.task is task)
        assert len(tasks) == 1, "graph produced multiple tasks, one expected"
        proxy = tasks[0]
        task = proxy.task

        click.echo("  Cache")
        click.echo("    Identity          {0}".format(proxy.identity))
        if acache.is_available_locally(proxy):
            with acache.get_artifact(proxy) as artifact:
                click.echo("    Location          {0}".format(artifact.path))
            click.echo("    Local             True ({0})".format(
                utils.as_human_size(acache.get_artifact(proxy).get_size())))
        else:
            click.echo("    Local             False")
        click.echo("    Remote            {0}".format(acache.is_available_remotely(proxy)))
        click.echo()

    if influence:
        click.echo("  Influence")
        for string in HashInfluenceRegistry.get().get_strings(task):
            string = string.split(":", 1)
            click.echo("    {:<18}{}".format(string[0][10:], string[1].strip()))
