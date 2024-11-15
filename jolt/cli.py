import atexit
import click
import datetime
import os
import platform
import subprocess
import sys
import uuid
import webbrowser

from jolt.tasks import Task, TaskRegistry, Parameter
from jolt import scheduler
from jolt import graph
from jolt import cache
from jolt import colors
from jolt import filesystem as fs
from jolt import log
from jolt import __version__
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
workdir = os.getcwd()


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
        if cmd_name == "info":
            cmd_name = "inspect"

        if cmd_name in ["export", "inspect"]:
            log.set_level(log.SILENCE)
        elif ctx.params.get("verbose") >= 3:
            log.set_level(log.EXCEPTION)
        elif ctx.params.get("verbose") >= 2:
            log.set_level(log.DEBUG)
        elif ctx.params.get("verbose") >= 1:
            log.set_level(log.VERBOSE)

        config_files = ctx.params.get("config_file") or []
        for config_file in config_files:
            log.verbose("Config: {0}", config_file)
            config.load_or_set(config_file)

        # Load configured plugins
        JoltLoader.get().load_plugins()

        return click.Group.get_command(self, ctx, cmd_name)


@click.group(cls=PluginGroup, invoke_without_command=True)
@click.version_option(__version__)
@click.option("-v", "--verbose", count=True, help="Verbose output (repeat to raise verbosity).")
@click.option("-c", "--config", "config_file", multiple=True, type=str,
              help="Load a configuration file or set a configuration key.")
@click.option("-C", "--chdir", type=str,
              help="Change working directory before executing command.")
@click.option("--interpreter", "machine_interface", type=str, help="Used for debugging.", hidden=True)
@click.option("-d", "--debugger", is_flag=True,
              help="Attach debugger on exception.")
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
@click.option("-h", "--help", is_flag=True, help="Show this message and exit.")
@click.pass_context
def cli(ctx, verbose, config_file, debugger, profile,
        force, salt, debug, network, local, keep_going, jobs, help, machine_interface, chdir):
    """
    A task execution tool.

    When invoked without any commands and arguments, Jolt by default tries
    to execute and build the artifact of a task called `default`. To build
    artifacts of other tasks use the build subcommand.

    The Jolt command line interface is hierarchical. One set of options
    can be passed to the top-level command and a different set of options
    to the subcommands, simultaneously. For example, verbose output is
    a top-level option while forced rebuild is a build command option.
    They may combined like this:

      $ jolt --verbose build --force taskname

    Most build command options are available also at the top-level when
    build is invoked implicitly for the default task.

    """

    global debug_enabled
    debug_enabled = debugger

    if machine_interface:
        log.enable_gdb()

    if ctx.invoked_subcommand not in ["log", "report"]:
        log.start_file_log()

    if chdir:
        global workdir
        workdir = chdir
        os.chdir(workdir)

    log.verbose("Jolt version: {}", __version__)
    log.verbose("Jolt command: {}", " ".join([fs.path.basename(sys.argv[0])] + sys.argv[1:]))
    log.verbose("Jolt host: {}", os.environ.get("HOSTNAME", "localhost"))
    log.verbose("Jolt install path: {}", fs.path.dirname(__file__))
    log.verbose("Jolt workdir: {}", workdir)

    if ctx.invoked_subcommand in ["config", "executor", "log"]:
        # Don't attempt to load any task recipes as they might require
        # plugins that are not yet configured.
        return

    if ctx.invoked_subcommand is None:
        build = ctx.command.get_command(ctx, "build")

    if help:
        print(ctx.get_help())
        sys.exit(0)

    manifest = JoltManifest()
    utils.call_and_catch(manifest.parse)
    manifest.process_import()
    ctx.obj["manifest"] = manifest

    if manifest.version:
        from jolt.version_utils import requirement, version
        req = requirement(manifest.version)
        ver = version(__version__)
        raise_error_if(not req.satisfied(ver),
                       "This project requires Jolt version {} (running {})",
                       req, __version__)

    loader = JoltLoader.get()
    tasks = loader.load()
    for cls in tasks:
        TaskRegistry.get().add_task_class(cls)

    if ctx.invoked_subcommand in ["build", "clean"] and loader.joltdir:
        ctx.obj["workspace_lock"] = utils.LockFile(
            loader.build_path,
            log.info, "Workspace is locked by another process, please wait...")
        atexit.register(ctx.obj["workspace_lock"].close)

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
@click.argument("task", type=str, nargs=-1, shell_complete=_autocomplete_tasks, cls=ArgRequiredUnless, required_unless="worker")
@click.option("-c", "--copy", type=click.Path(),
              help="Copy artifact content to directory PATH.")
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.", metavar="DEFAULT")
@click.option("-f", "--force", is_flag=True, default=False, help="Force rebuild of TASK artifact.")
@click.option("-g", "--debug", is_flag=True, default=False,
              help="Start debug shell before executing TASK.")
@click.option("-j", "--jobs", type=int, default=1, help="Number of tasks allowed to execute in parallel [1]. ", metavar="JOBS")
@click.option("-k", "--keep-going", is_flag=True, default=False, help="Build as many task artifacts as possible.")
@click.option("-l", "--local", is_flag=True, default=False, help="Disable remote cache access.")
@click.option("-n", "--network", is_flag=True, default=False, help="Distribute tasks to network workers.")
@click.option("-s", "--salt", type=str, help="Add salt as hash influence for all tasks in dependency tree.", metavar="SALT")
@click.option("-m", "--mute", is_flag=True, help="Display task log only if it fails.")
@click.option("-v", "--verbose", count=True, help="Verbose output (repeat to raise verbosity).")
@click.option("--result", type=click.Path(), hidden=True,
              help="Write result manifest to this file.")
@click.option("--no-download", is_flag=True, default=False,
              help="Don't download any artifacts from remote storage")
@click.option("--no-download-persistent", is_flag=True, default=False,
              help="Don't download persistent artifacts from remote storage (only session artifacts)")
@click.option("--no-upload", is_flag=True, default=False,
              help="Don't upload artifacts to remote storage")
@click.option("--download", is_flag=True, default=False,
              help="Do download artifacts from remote storage")
@click.option("--upload", is_flag=True, default=False,
              help="Do upload artifacts to remote storage")
@click.option("--no-prune", is_flag=True, default=False,
              help="Don't prune cached artifacts from the build graph. This option can be used to populate the local cache with remotely cached dependency artifacts.")
@click.option("--worker", is_flag=True, default=False,
              help="Run with the worker build strategy", hidden=True)
@click.pass_context
@hooks.cli_build
def build(ctx, task, network, keep_going, default, local,
          no_download, no_download_persistent, no_upload, download, upload, worker, force,
          salt, copy, debug, result, jobs, no_prune, verbose,
          mute):
    """
    Build task artifact.

    TASK is the name of the task to execute. It is optionally followed by a colon and
    parameter value assignments. Assignments are separated by commas. Example:

       taskname:param1=value1,param2=value2

    Default parameter values can be overridden for any task in the dependency tree
    with --default. DEFAULT is a qualified task name, just like TASK, but parameter
    assignments change default values.

    By default, a task is executed locally and the resulting artifact is stored
    in the local artifact cache. If an artifact is already available in the cache,
    no execution takes place. Artifacts are identified with a hash digest,
    constructed from hashing task attributes.

    When remote cache providers are configured, artifacts may be downloaded from and/or
    uploaded to the remote cache as execution progresses. Several options exist to control
    the behavior, such as --local which disables all remote caches.

    Distributed task execution is enabled by passing the --network option. Tasks are then
    distributed to and executed by a pool of workers, if one has been configured.

    Rebuilds can be forced with either --force or --salt. --force rebuilds the requested
    task, but not its dependencies. --salt affects the entire dependency tree. Both add
    an extra attribute to the task hash calculation in order to taint the identity and
    induce a cache miss. In both cases, existing intermediate files in build directories
    are removed before execution starts.

    """
    raise_error_if(network and local,
                   "The -n and -l flags are mutually exclusive")

    raise_error_if(network and debug,
                   "The -g and -n flags are mutually exclusive")

    raise_error_if(no_download and download,
                   "The --download and --no-download flags are mutually exclusive")

    raise_error_if(no_upload and upload,
                   "The --upload and --no-upload flags are mutually exclusive")

    if verbose >= 3:
        log.set_level(log.EXCEPTION)
    elif verbose >= 2:
        log.set_level(log.DEBUG)
    elif verbose >= 1:
        log.set_level(log.VERBOSE)

    ts_start = utils.duration()
    task = list(task)
    task = [utils.stable_task_name(t) for t in task]

    if network:
        _download = config.getboolean("network", "download", True)
        _upload = config.getboolean("network", "upload", True)
    else:
        _download = config.getboolean("jolt", "download", True)
        _upload = config.getboolean("jolt", "upload", True)
    _download_session = _download

    if local:
        _download = False
        _upload = False
    else:
        if no_download:
            _download = False
            _download_session = False
        if no_download_persistent:
            _download = False
        if no_upload:
            _upload = False
        if download:
            _download = True
            _download_session = True
        if upload:
            _upload = True

    if keep_going:
        config.set_keep_going(True)

    options = JoltOptions(
        network=network,
        local=local,
        download=_download,
        download_session=_download_session,
        upload=_upload,
        keep_going=keep_going,
        default=default,
        worker=worker,
        debug=debug,
        salt=salt,
        jobs=jobs,
        mute=mute)

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

    log.info("Started: {}", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    gb = graph.GraphBuilder(registry, acache, manifest, options, progress=True)
    dag = gb.build(task)

    # Collect information about artifact presence before starting prune or build
    acache.precheck(dag.persistent_artifacts, remote=not local)

    if not no_prune:
        gp = graph.GraphPruner(acache, strategy)
        dag = gp.prune(dag)

    goal_tasks = dag.goals
    goal_task_duration = 0

    session = executors.create_session(dag) if options.network else {}
    queue = scheduler.TaskQueue(strategy, acache, session)

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
            while dag.has_tasks() or not queue.empty():
                # Find all tasks ready to be executed
                leafs = dag.select(lambda graph, task: task.is_ready())

                # Order the tasks by their weights to improve build times
                leafs.sort(key=lambda x: x.weight)

                while leafs:
                    task = leafs.pop()
                    queue.submit(task)

                task, error = queue.wait()

                if not task:
                    dag.debug()
                    break
                elif task.is_goal() and task.duration_running:
                    goal_task_duration += task.duration_running.seconds

                # Unpack tasks with overridden unpack() method
                if not task.is_resource():
                    if no_prune and task.task.unpack.__func__ is not Task.unpack:
                        with acache.get_context(task):
                            pass

                    progress.update(1)

                if no_prune and task.is_workspace_resource():
                    task.task.acquire_ws(force=True)

                if not keep_going and error is not None:
                    queue.abort()
                    task.raise_for_status()
                    raise error

        if dag.failed or dag.unstable:
            log.error("List of failed tasks")
            for failed in dag.failed + dag.unstable:
                log.error("- {}", failed.log_name.strip("()"))

        for failed_task in dag.failed:
            failed_task.raise_for_status()
        if dag.failed:
            raise_error("No more tasks could be executed")

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

        for task in goal_tasks:
            for artifact in task.artifacts:
                if acache.is_available_locally(artifact):
                    log.info("Location: {0}", artifact.path)
                    if copy:
                        dst = utils.as_dirpath(fs.path.join(workdir, click.format_filename(copy)))
                        artifact.copy("*", dst, symlinks=True)

        log.info("Ended: {}", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        log.info("Total execution time: {0} {1}",
                 str(ts_start),
                 str(queue.duration_acc) if network else '')
        if result:
            with report.update() as manifest:
                manifest.duration = str(goal_task_duration)
                manifest.write(result)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False, shell_complete=_autocomplete_tasks)
@click.option("-d", "--deps", is_flag=True, help="Clean all task dependencies.")
@click.option("-e", "--expired", is_flag=True, help="Only clean expired tasks.")
@click.pass_context
@hooks.cli_clean
def clean(ctx, task, deps, expired):
    """
    Delete task artifacts and intermediate files.

    When run without arguments, this command removes all task artifacts
    from the local cache, but no intermediate files are removed.

    When TASK is specified, the task clean() method is invoked to remove
    any intermediate files still present in persistent build directories.
    Secondly, the task artifact will be removed from the local cache.
    Global caches are not affected. The --deps parameter can be used to also
    clean all dependencies of the specified TASK.

    By default, task artifacts are removed without considering any
    artifact expiration metadata. To only remove artifact which have expired,
    use the --expired parameter. Artifacts typically expire immediately after
    creation unless explicitly configured not to.
    """
    acache = cache.ArtifactCache.get()
    if task:
        task = [utils.stable_task_name(t) for t in task]
        registry = TaskRegistry.get()
        dag = graph.GraphBuilder(registry, acache, ctx.obj["manifest"]).build(task)
        if deps:
            tasks = dag.tasks
        else:
            tasks = dag.goals
        for task in tasks:
            task.clean(acache, expired)
    else:
        acache.discard_all(expired, onerror=fs.onerror_warning)
        try:
            # May not be in a workspace when running the command
            t = tools.Tools()
            fs.rmtree(t.buildroot, onerror=fs.onerror_warning)
        except AssertionError:
            pass


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
        raise_error_if(value is None, "No such key: {}".format(key))
        print("{} = {}".format(key, value))

    def _print_section(section):
        print("{}".format(section))

    if list:
        for section, option, value in config.items(alias):
            if option:
                print("{}.{} = {}".format(section, option, value))
            else:
                print(section)
    elif delete:
        raise_error_if(config.delete(key, alias) <= 0,
                       "No such key: {}", key)
        config.save()
    elif key:
        section, opt = config.split(key)
        if value:
            raise_error_if(opt is None, "Invalid configuration key: {}".format(key))
            config.set(section, opt, value, alias)
            try:
                config.save()
            except Exception as e:
                log.exception()
                raise_error("Failed to write configuration file: {}".format(e))
        else:
            if opt:
                _print_key(section, opt)
            else:
                _print_section(section)


@cli.command()
@click.argument("task", type=str, nargs=-1, required=False, shell_complete=_autocomplete_tasks)
@click.option("-c", "--cached", "show_cache", is_flag=True, help="Highlight cache presence with colors.")
@click.option("-r", "--reverse", type=str, help="Display consumers of REVERSE if TASK is executed.")
@click.option("-p", "--prune", "prune", is_flag=True, help="Do not repeat tasks. An already visited task's name is printed inside [square brackets] and its deps are omitted.")
@click.pass_context
def display(ctx, task, reverse=None, show_cache=False, prune=False):
    """
    Display a task and its dependencies visually.

    """
    registry = TaskRegistry.get()
    options = JoltOptions()
    acache = cache.ArtifactCache.get(options)
    gb = graph.GraphBuilder(registry, acache, ctx.obj["manifest"])
    dag = gb.build(task, influence=show_cache)

    if reverse:
        def iterator(task):
            return list(dag.predecessors(task))
        reverse = utils.as_list(reverse)
        tasklist = dag.select(
            lambda graph, node:
            node.short_qualified_name in reverse or node.qualified_name in reverse)
    else:
        def iterator(task):
            return task.children
        tasklist = dag.requested_goals

    if dag.has_tasks():
        processed = set()

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

            if prune and task.short_qualified_name in processed:
                def prune_marker(n):
                    return "[" + n + "]"
            else:
                def prune_marker(n):
                    return n

            print(header + colorize(prune_marker(task.short_qualified_name)))
            children = iterator(task)
            if not prune or task.short_qualified_name not in processed:
                for i in range(0, len(children)):
                    _display(children[i], indent + 1, last=(last or []) + [i + 1 != len(children)])

            if prune:
                processed.add(task.short_qualified_name)

        for task in tasklist:
            _display(task)
    else:
        log.info("no tasks to display")


@cli.command()
def docs():
    """
    Opens the Jolt documentation in the default webbrowser.
    """
    url = config.get("jolt", "docs", "http://jolt.readthedocs.io/")
    success = False
    try:
        success = webbrowser.open(url)
    except Exception:
        pass
    if not success:
        print(f"Failed to open web browser. Visit {url} manually.")


@cli.command()
@click.argument("task", type=str, nargs=-1, required=True, shell_complete=_autocomplete_tasks)
@click.option("-c", "--copy", type=click.Path(),
              help="Copy artifact content to directory PATH.")
@click.option("-ca", "--copy-all", type=click.Path(), help="Copy artifacts, including dependency artifacts, to directory PATH. Implies --deps.")
@click.option("-d", "--deps", is_flag=True, help="Download dependencies.")
@click.pass_context
@hooks.cli_download
def download(ctx, task, deps, copy, copy_all):
    """
    Download task artifacts from remote caches.

    No attempt to build the artifact is made if it is not present
    in configured remote caches.

    Task dependencies may optionally be downloaded by passing the -d option.
    """

    raise_error_if(copy and copy_all, "--copy and --copy-all are mutually exclusive")
    if copy_all:
        deps = True

    manifest = ctx.obj["manifest"]
    options = JoltOptions()
    acache = cache.ArtifactCache.get(options)
    hooks.TaskHookRegistry.get(options)
    executors = scheduler.ExecutorRegistry.get(options)
    registry = TaskRegistry.get()
    strategy = scheduler.DownloadStrategy(executors, acache)
    queue = scheduler.TaskQueue(strategy, acache, {})
    gb = graph.GraphBuilder(registry, acache, manifest, options, progress=True)
    dag = gb.build(task)

    if not deps:
        for task in dag.tasks:
            if not task.is_goal():
                task.pruned()

    all_tasks = dag.tasks
    goal_tasks = dag.goals

    try:
        with log.progress("Progress", dag.number_of_tasks(), " tasks", estimates=False, debug=False) as p:
            while dag.has_tasks() or not queue.empty():
                leafs = dag.select(lambda graph, task: task.is_ready())

                while leafs:
                    task = leafs.pop()
                    queue.submit(task)

                task, error = queue.wait()
                p.update(1)

        copy_tasks = goal_tasks if not copy_all else all_tasks
        for goal in copy_tasks:
            if goal.is_available_locally():
                for artifact in goal.artifacts:
                    if copy:
                        log.info("Copying: {0}", artifact.path)
                        artifact.copy("*", utils.as_dirpath(fs.path.join(workdir, click.format_filename(copy))), symlinks=True)
                    elif copy_all:
                        log.info("Copying: {0}", artifact.path)
                        artifact.copy("*", utils.as_dirpath(fs.path.join(workdir, click.format_filename(copy_all))), symlinks=True)
                    elif goal.is_goal():
                        log.info("Location: {0}", artifact.path)

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

    gb = graph.GraphBuilder(registry, acache, manifest)
    dag = gb.build(task)

    available, missing = acache.availability(dag.persistent_artifacts)

    for artifact in missing:
        raise_task_error_if(
            not remove, artifact.get_task(),
            "Task artifact is not available in any cache, build it first")

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
@click.argument("task", type=str, nargs=-1, required=False, shell_complete=_autocomplete_tasks)
@click.option("-a", "--all", is_flag=True, help="List all direct and indirect dependencies of TASK.")
@click.option("-r", "--reverse", type=str, help="Only list dependencies of TASK that are also reverse dependencies of REVERSE.", metavar="REVERSE")
@click.pass_context
def _list(ctx, task=None, all=False, reverse=None):
    """
    List all tasks, or dependencies of a task.

    By default, when no TASK is specified, all known task names
    are listed in alphabetical order.

    When a TASK is specified, only direct dependencies of that task
    are listed. Use -a to also list its indirect dependencies.

    Multiple TASK names are allowed.
    """

    raise_error_if(not task and reverse, "TASK required with --reverse")

    options = JoltOptions()
    acache = cache.ArtifactCache.get(options)
    registry = TaskRegistry.get()

    if not task:
        classes = registry.get_task_classes()
        for task in sorted(classes, key=lambda x: x.name):
            if task.name:
                print(task.name)
        return

    task = [utils.stable_task_name(t) for t in task]
    reverse = [utils.stable_task_name(t) for t in utils.as_list(reverse or [])]

    try:
        dag = graph.GraphBuilder(registry, acache, ctx.obj["manifest"]).build(task, influence=False)
    except JoltError as e:
        raise e
    except Exception:
        raise_error("An exception occurred during task dependency evaluation, see log for details")

    task = reverse or task
    nodes = dag.select(
        lambda graph, node:
        node.short_qualified_name in task or node.qualified_name in task)
    nodes = list(nodes)
    iterator = dag.predecessors if reverse else dag.successors

    tasklist = set()
    while nodes:
        node = nodes.pop()
        for task in iterator(node):
            if all and task.short_qualified_name not in tasklist:
                new_node = dag.get_task(task.qualified_name)
                nodes.append(new_node)
            tasklist.add(task.short_qualified_name)

    for task in sorted(list(tasklist)):
        print(task)


@cli.command(name="log")
@click.option("-f", "--follow", is_flag=True, help="Display log output as it appears")
@click.option("-d", "--delete", is_flag=True, help="Delete the log file")
def _log(follow, delete):
    """
    Display the Jolt log file.

    """
    if not log.logfiles:
        print("No logs exist")
        return

    if follow:
        subprocess.call("tail -f {0}".format(log.logfiles[-1]), shell=True)
    elif delete:
        for file in log.logfiles:
            fs.unlink(file)
    else:
        t = tools.Tools()
        configured_pager = config.get("jolt", "pager", os.environ.get("PAGER", None))
        for pager in [configured_pager, "less", "more", "cat"]:
            if pager and t.which(pager):
                return subprocess.call("{1} {0}".format(log.logfiles[-1], pager), shell=True)
        print(t.read_file(logfile))


@cli.command()
@click.argument("task", shell_complete=_autocomplete_tasks)
@click.option("-i", "--influence", is_flag=True, help="Print influence attributes and values.")
@click.option("-a", "--artifact", is_flag=True, help="Print artifact cache status.")
@click.option("-s", "--salt", type=str, help="Add salt as task influence.", metavar="SALT")
@click.pass_context
def inspect(ctx, task, influence=False, artifact=False, salt=None):
    """
    View information about a task.

    This command displays information about a task, such as its class
    documentation, parameters and their accepted values, requirements,
    task class origin (file/line), influence attributes, artifact identity,
    cache status, and more. Default parameter values, if any, are highlighted.

    """
    task_name = task
    task_cls_name, task_params = utils.parse_task_name(task_name)
    task_registry = TaskRegistry.get()
    task = task_registry.get_task_class(task_cls_name)
    raise_task_error_if(not task, task_name, "No such task")

    from jolt import inspection

    print()
    print("  {0}".format(task.name))
    print()
    if task.__doc__:
        print("  {0}".format(task.__doc__.strip()))
        print()
    print("  Parameters")
    has_param = False
    params = {key: getattr(task, key) for key in dir(task)
              if isinstance(utils.getattr_safe(task, key), Parameter)}
    for item, param in params.items():
        has_param = True
        print("    {0:<15}   {1}".format(item, param.help or ""))
    if not has_param:
        print("    None")

    print()
    print("  Definition")
    print("    {0:<15}   {1} ({2})".format(
        "File", fs.path.relpath(inspection.getfile(task), JoltLoader.get().joltdir),
        inspection.getlineno(task)))

    print()
    print("  Requirements")
    manifest = ctx.obj["manifest"]
    try:
        task = task_registry.get_task(task_name, manifest=manifest)
        for req in sorted(utils.as_list(utils.call_or_return(task, task.requires))):
            print("    {0}".format(task.tools.expand(req)))
        if not task.requires:
            print("    None")
        print()
    except Exception as e:
        log.exception()
        if "has not been set" in str(e):
            print("    Unavailable (parameters must be set)")
            print()
            return
        print("    Unavailable (exception during evaluation)")
        print()
        return

    if salt:
        task.taint = salt

    if artifact:
        options = JoltOptions(salt=salt)
        acache = cache.ArtifactCache.get()
        builder = graph.GraphBuilder(task_registry, acache, manifest, options)
        dag = builder.build([task.qualified_name])
        tasks = dag.select(lambda graph, node: node.task is task)
        assert len(tasks) == 1, "graph produced multiple tasks, one expected"
        proxy = tasks[0]
        task = proxy.task

        print("  Cache")
        print("    Identity          {0}".format(proxy.identity))
        if proxy.is_available_locally():
            for artifact in filter(lambda a: not a.is_session(), proxy.artifacts):
                print("    Location          {0}".format(artifact.path))
            print("    Local             True ({0})".format(
                utils.as_human_size(sum([artifact.get_size() for artifact in proxy.artifacts]))))
        else:
            print("    Local             False")
        print("    Remote            {0}".format(proxy.is_available_remotely(cache=False)))
        print()

    if influence:
        print("  Influence")
        for string in HashInfluenceRegistry.get().get_strings(task):
            string = string.split(":", 1)
            print("    {:<18}{}".format(string[0][10:], string[1].strip()))


@cli.command()
@click.argument("task", type=str, nargs=-1, required=True, shell_complete=_autocomplete_tasks)
@click.pass_context
def export(ctx, task):
    """
    Export task artifact metadata into shell environment.

    When running the command, a shell script is printed to stdout.
    It can be redirected to a file and executed separately, or sourced
    directly in the shell by running:

      source <(jolt export <task>)

    The script creates a virtual environment that is identical
    to the environment that would be setup when the specified task
    artifact is consumed by another task. This enables packaged
    applications, such as compilers, to be run directly from the shell.

    The command will fail if the task artifact or any dependency
    artifact is missing in the local cache. Build the task to
    populate the cache and then try again.

    Run ``deactivate-jolt`` to leave the virtual environment. All
    environment variables will be restored to their original values.
    """
    try:
        _export(ctx, task)
    finally:
        log.set_level(log.INFO)


def _export(ctx, task):
    acache = cache.ArtifactCache.get()
    task = [utils.stable_task_name(t) for t in task]
    registry = TaskRegistry.get()
    executors = scheduler.ExecutorRegistry.get()
    strategy = scheduler.LocalStrategy(executors, acache)

    dag = graph.GraphBuilder(registry, acache, ctx.obj["manifest"])
    dag = dag.build(task)

    gp = graph.GraphPruner(acache, strategy)
    dag = gp.prune(dag)

    class Export(object):
        def __init__(self):
            self.environ = {}
            self.prepend_environ = {}

        def setenv(self, name, value):
            self.environ[name] = value

    class Context(object):
        def __init__(self, tasks):
            self.tasks = tasks
            self.environ = set()
            self.exports = {}

        def add_export(self, task, visitor):
            self.exports[task] = visitor
            self.environ.update(set(visitor.environ.keys()))

    tasks = list(filter(lambda t: t.is_cacheable(), reversed(dag.topological_nodes)))
    context = Context(tasks)

    for task in context.tasks:
        for artifact in task.artifacts:
            raise_task_error_if(
                artifact.is_temporary(), task,
                "Task artifact not found in local cache, build it first")

            visitor = Export()
            cache.visit_artifact(task, artifact, visitor)
            context.add_export(task, visitor)

    script = utils.render(
        "export.sh.template",
        ctx=context)

    print(script)


@cli.command(name="report")
@click.pass_context
@hooks.cli_report
def _report(ctx):
    """Create and publish a report with system information and logs.

    The purpose of the report command is to aid troubleshooting by
    providing users a method to quickly generate and share a report
    with information about the environment and previous activity.

    The report is uploaded to remote caches if configured, otherwise
    a report archive is created in the current working directory.
    """

    options = JoltOptions()
    acache = cache.ArtifactCache.get(options)

    with tools.Tools() as t:

        artifact = cache.Artifact(
            acache,
            None,
            identity=str(uuid.uuid4()),
            name="jolt",
            session=True,
            tools=t)

        with t.tmpdir("report") as tmp, t.cwd(tmp):
            log.info("Collecting environment")
            env = ""
            for key, val in os.environ.items():
                env += f"{key} = {val}\n"
            t.write_file("environ.txt", env, expand=False)

            log.info("Collecting configuration")
            config.save(tmp)
            artifact.collect("*.conf", "configs/")

            log.info("Collecting platform information")
            uname = platform.uname()
            libc = " ".join(platform.libc_ver())
            pyver = platform.python_version()
            pyimpl = platform.python_implementation()
            pfm = f"""System: {uname.system}
Node: {uname.node}
Release: {uname.release}
Version: {uname.version}
Machine: {uname.machine}
Libc: {libc}
Python: {pyimpl} {pyver}
"""
            t.write_file("platform.txt", pfm, expand=False)

            def collect_command(what, cmd):
                try:
                    log.info("Collecting {}", what)
                    t.run(cmd, output=False)
                except Exception:
                    pass

            collect_command("pip modules", "pip list > packages-pip.txt")
            if uname.system == "Linux":
                collect_command("apt packages", "apt list --installed > packages-apt.txt")
                artifact.collect("/etc/os-release", "os-release.txt")
            artifact.collect("*.txt")

        with t.cwd(log.logpath):
            artifact.collect("*.log", "logs/")

        acache.commit(artifact)
        if acache.upload_enabled():
            assert acache.upload(artifact)
            url = acache.location(artifact)
        else:
            url = f"{artifact.identity}.tgz"
            t.archive(artifact.path, url)

        log.info("Location: {}", url)
