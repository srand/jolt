import click
import grpc
import queue
from threading import Lock
import time

from google.protobuf.timestamp_pb2 import Timestamp

from jolt import cache
from jolt import cli
from jolt import colors
from jolt import config
from jolt import hooks
from jolt import loader
from jolt import log
from jolt import common_pb2 as common_pb
from jolt import scheduler
from jolt import utils
from jolt.error import LoggedJoltError, JoltError, raise_error, raise_error_if, raise_task_error, raise_task_error_if
from jolt.graph import GraphBuilder
from jolt.scheduler import ExecutorRegistry, JoltEnvironment, NetworkExecutor, NetworkExecutorFactory, WorkerStrategy
from jolt.tasks import TaskRegistry
from jolt.options import JoltOptions
from jolt.plugins import selfdeploy
from jolt.plugins.remote_execution import log_pb2 as log_pb
from jolt.plugins.remote_execution import log_pb2_grpc as log_grpc
from jolt.plugins.remote_execution import scheduler_pb2 as scheduler_pb
from jolt.plugins.remote_execution import scheduler_pb2_grpc as scheduler_grpc
from jolt.plugins.remote_execution import worker_pb2_grpc as worker_grpc


NAME = "scheduler"
TYPE = "Remote execution"


def locked(func):
    """ Decorator to lock a method. """
    def _f(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
    return _f


class LogHandler(object):
    """
    Log handler for executors.

    The handler is installed in the log module and sends log messages to the
    scheduler. The scheduler then forwards the messages to the client.

    The handler is installed for the duration of the task execution.
    """

    def __init__(self, stream, task):
        self.stream = stream
        self.task = task
        self.level = log.EXCEPTION

    def emit(self, record):
        """ No log messages are emitted. """
        pass

    def handle(self, record):
        """
        Handle a log record.

        The log record is formatted and sent to the scheduler.
        """
        try:
            record.message = record.msg.format(*record.args)
        except Exception:
            record.message = record.msg

        timestamp = Timestamp()
        timestamp.FromNanoseconds(int(record.created * 1000000000))

        self.stream.push(
            scheduler_pb.TaskUpdate(
                request=self.task,
                status=common_pb.TaskStatus.TASK_RUNNING,
                loglines=[
                    common_pb.LogLine(
                        context=self.task.task_id[:8],
                        level=log.level_to_pb(record.levelno),
                        time=timestamp,
                        message=record.message,
                    ),
                ]
            )
        )

    def createLock(self):
        """ Return a lock. """
        return None


class TaskCancelledException(JoltError):
    """ An exception raised when a task is cancelled by the scheduler. """
    pass


class Queue(object):
    """ A simple queue that can be used to send messages to the scheduler. """

    def __init__(self):
        self.q = queue.Queue()

    def __next__(self):
        """ Get the next item from the queue. """
        data = self.q.get()
        if data is None:
            raise StopIteration
        return data

    def push(self, item):
        """ Push an item to the queue. """
        self.q.put(item)

    def close(self):
        self.q.put(None)


class RemoteExecutor(NetworkExecutor):
    """
    Executor for remotely executed tasks.

    The executor schedules the task with the scheduler and waits for the
    scheduler to respond with a task id. The executor then waits for the
    scheduler to respond with task updates. Log messages are forwarded to the
    logging system where they are formatted and emitted.

    The executor is responsible for downloading persistent artifacts from the
    cache. The executor will not download persistent artifacts unless the
    task is marked as successfully completed.

    The executor is also responsible for downloading session artifacts from the
    cache. The executor will attempt download session artifacts regardless of the
    task status. No error is raised if the download fails.

    """

    def __init__(self, factory, session, task):
        self.factory = factory
        self.session = session
        self.task = task

    def schedule(self, env):
        """
        Schedule the task for execution.

        The task is marked as in progress before scheduling.
        """
        self.task.set_in_progress()
        return super().schedule(env)

    def cancel(self):
        """
        Cancel the build session.

        The build session will be cancelled if the task is cancelled.
        """
        self.session.cancel()

    def download_persistent_artifacts(self, task):
        """ Download persistent artifacts from the cache. """

        for extension in task.extensions:
            self.download_persistent_artifacts(extension)
        if not task.has_artifact():
            return
        if not task.cache.download_enabled():
            return
        if not task.is_downloadable():
            return
        raise_task_error_if(
            not task.download(persistent_only=True), task,
            "Failed to download artifact")

    def download_session_artifacts(self, task):
        """ Download session artifacts from the cache. """

        for extension in task.extensions:
            self.download_session_artifacts(extension)
        if not task.has_artifact():
            return
        if not task.cache.download_session_enabled():
            return
        if not task.is_downloadable():
            return
        if not task.download(session_only=True):
            task.warning("Failed to download session artifact")
        if not task.is_resource():
            # Tasks also download session artifacts of consumed resources
            for resource in filter(lambda task: task.is_resource() and not task.is_workspace_resource(), task.children):
                if not resource.is_available_locally(persistent_only=False):
                    self.download_session_artifacts(resource)

    def download_log(self, task):
        """ Download log and transfer lines into local logging system. """
        request = log_pb.ReadLogRequest(
            id=task.instance,
        )
        for response in self.session.logs.ReadLog(request):
            for line in response.loglines:
                log.log(
                    log.pb_to_level(line.level),
                    line.message,
                    created=line.time.ToMicroseconds() / 1000000,
                    context=line.context[:7],
                    prefix=True)

    def update_logstash(self, task):
        """ Update logstash with the task status. """
        self.task.logstash = self.session.http_uri + "/logs/" + self.task.instance

    def run(self, env):
        """ Run the task. """
        if self.is_aborted():
            return
        try:
            with hooks.task_run([self.task] + self.task.extensions), self.task.run_resources():
                try:
                    self.run_build(env)
                except (grpc.RpcError, grpc._channel._MultiThreadedRendezvous) as rpc_error:
                    raise_task_error(self.task, rpc_error.details(), type="Scheduler Error")
        except Exception as e:
            if not self.task.is_unstable:
                raise e
        finally:
            self.download_session_artifacts(self.task)

    @utils.retried.on_exception(grpc.RpcError)
    def run_build(self, env):
        """ Initialize the build session and schedule the task. """

        try:
            self.session.make_build_request()

            self.task.queued(remote=True)
            for extension in self.task.extensions:
                extension.queued(remote=True)

            request = scheduler_pb.TaskRequest(
                build_id=self.session.build_id,
                task_id=self.task.identity,
            )
            response = self.session.exec.ScheduleTask(request)

            self.update_logstash(self.task)
            self.run_task(env, response)
            self.download_persistent_artifacts(self.task)

            self.task.finished_execution(remote=True)
            for extension in self.task.extensions:
                extension.finished_execution(remote=True)

        except TaskCancelledException:
            pass

        except (grpc.RpcError, grpc._channel._MultiThreadedRendezvous) as rpc_error:
            if self.is_aborted():
                if self.task.is_running():
                    self.task.failed_execution(remote=True, interrupt=True)
                    for extension in self.task.extensions:
                        extension.failed_execution(remote=True, interrupt=True)
                return

            if rpc_error.code() not in [grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNAVAILABLE]:
                raise_task_error(self.task, rpc_error.details(), type="Scheduler Error")

            self.session.clear_build_request(f"Scheduler Error: {rpc_error.details()}")
            raise rpc_error

        except Exception as e:
            if not isinstance(e, LoggedJoltError):
                log.exception()

            if self.factory.options.mute:
                try:
                    self.download_log(self.task)
                except Exception:
                    self.task.warning("Failed to download build log")

            self.task.failed_execution(remote=True)
            for extension in self.task.extensions:
                extension.failed_execution(remote=True)

            raise e

    def run_task(self, env, response):
        """ Run the task.

        Task updates are received from the scheduler and forwarded to the
        logging system. The task is marked as running when the scheduler
        responds with a task running status.

        A change in task status is used to determine when the task has
        completed. The task is marked as completed when the scheduler
        responds with a task passed, skipped, downloaded, or uploaded status.
        An exception is raised if the scheduler responds with a task error,
        failed, unstable, or cancelled status.
        """

        last_status = common_pb.TaskStatus.TASK_QUEUED

        for progress in response:
            for line in progress.loglines:
                log.log(
                    log.pb_to_level(line.level),
                    line.message,
                    created=line.time.ToMicroseconds() / 1000000,
                    context=line.context[:7],
                    prefix=True)

            if progress.worker:
                self.task.worker = progress.worker.hostname

            if progress.status in [common_pb.TaskStatus.TASK_RUNNING] \
               and progress.status != self.task.status():
                self.task.running_execution(remote=True)
                for extension in self.task.extensions:
                    extension.running_execution(remote=True)

            if progress.status in [common_pb.TaskStatus.TASK_QUEUED]:
                if last_status in [common_pb.TaskStatus.TASK_RUNNING]:
                    self.task.restarted_execution(remote=True)
                    for extension in self.task.extensions:
                        extension.restarted_execution(remote=True)

            if progress.status in [
                    common_pb.TaskStatus.TASK_PASSED,
                    common_pb.TaskStatus.TASK_DOWNLOADED,
                    common_pb.TaskStatus.TASK_UPLOADED,
                    common_pb.TaskStatus.TASK_SKIPPED,
            ]:
                break

            if progress.status in [common_pb.TaskStatus.TASK_CANCELLED]:
                if last_status in [common_pb.TaskStatus.TASK_RUNNING]:
                    self.task.failed_execution(remote=True, interrupt=True)
                    for extension in self.task.extensions:
                        extension.failed_execution(remote=True, interrupt=True)
                raise TaskCancelledException()

            if progress.status in [
                    common_pb.TaskStatus.TASK_FAILED,
                    common_pb.TaskStatus.TASK_UNSTABLE,
            ]:
                for error in progress.errors:
                    with self.task.task.report() as report:
                        report.add_error(
                            error.type,
                            error.location,
                            error.message,
                            error.details,
                        )
                self.task.raise_for_status()
                raise raise_error("Remote execution failed")

            if progress.status in [
                    common_pb.TaskStatus.TASK_ERROR,
            ]:
                log.log(
                    log.VERBOSE,
                    f"Host: {progress.worker.hostname}",
                    created=time.time(),
                    context=self.task.identity[:7],
                    prefix=True)

                for error in progress.errors:
                    with self.task.task.report() as report:
                        report.add_error(
                            error.type,
                            error.location,
                            error.message,
                            error.details,
                        )
                self.task.raise_for_status(log_details=not self.factory.options.mute)
                raise raise_error("Remote execution failed")

            last_status = progress.status


class RemoteSession(object):
    """
    A session with the scheduler.

    The session is responsible for establishing a connection with the scheduler,
    registering the build and creating task executors.
    """

    def __init__(self, factory):
        # Associated executor factory.
        self.factory = factory

        # Address of the scheduler.
        self.address = config.geturi(NAME, "uri", "tcp://scheduler.:9090")
        raise_error_if(self.address.scheme not in ["tcp"], "Invalid scheme in scheduler URI config: {}", self.address.scheme)
        raise_error_if(not self.address.netloc, "Invalid network address in scheduler URI config: {}", self.address.netloc)

        # URI of scheduler HTTP endpoints.
        self.http_uri = config.get(NAME, "http_uri", f"http://{self.address.netloc}")

        # GRPC channel.
        self.channel = grpc.insecure_channel(
            target=self.address.netloc,
        )

        # GRPC stub for the scheduler service.
        self.exec = scheduler_grpc.SchedulerStub(self.channel)

        # GRPC stub for the logstash service.
        self.logs = log_grpc.LogStashStub(self.channel)

        # Read build priority from config.
        # Higher priority builds will be scheduled first.
        # Default is 0.
        self.priority = config.getint(NAME, "priority", 0)

        # The build associated with this session.
        self.build = None
        self.build_id = None

        # Flag to indicate if the build has been aborted.
        self.aborted = False

        # Lock to ensure only one build is registered at a time.
        self.lock = Lock()

        # The build environment: client, workspace, etc.
        self.buildenv = None

    def initialize(self, graph):
        """ Initialize the session with the scheduler. """
        self.tasks = graph.tasks
        self.pruned = graph.pruned

    @locked
    @utils.retried.on_exception(grpc.RpcError)
    def make_build_request(self):
        """ Create a build request with the scheduler. """

        # If a build is already registered, return.
        if self.build:
            return

        if not self.buildenv:
            # Create the build environment.
            self.buildenv = common_pb.BuildEnvironment(
                client=selfdeploy.get_client(),
                parameters=config.export_params(),
                task_default_parameters=scheduler.export_task_default_params(self.tasks),
                tasks=scheduler.export_tasks(self.tasks + self.pruned),
                workspace=loader.export_workspace(self.tasks),
                loglevel=log.get_level_pb(),
                config=config.export_config(),
            )

        # Create the build request.
        req = scheduler_pb.BuildRequest(
            environment=self.buildenv,
            priority=self.priority,
            logstream=not self.factory.options.mute,
        )

        # Register the build with the scheduler.
        self.build = self.exec.ScheduleBuild(req)

        # Wait for the scheduler to respond with a build id.
        build = self.build.next()

        # Check if the build was rejected.
        if build.status == common_pb.BuildStatus.BUILD_REJECTED:
            raise_error("Build rejected by scheduler")

        # Store the build id.
        self.build_id = build.build_id

        log.info(colors.blue("Build registered with scheduler, waiting for worker"))
        return self.build

    @locked
    def clear_build_request(self, message=None):
        """ Clear the build request. Called when a build fails. """

        # Close grpc server response stream
        if self.build:
            self.build.cancel()
            if message:
                log.warning(message)
        self.build = None
        self.build_id = None

    def cancel(self):
        """ Send a cancel request to the scheduler. """

        # If the build has already been aborted, return.
        if self.aborted:
            return

        # If no build is registered, return.
        if not self.build:
            self.aborted = True
            return

        if not self.build_id:
            self.clear_build_request()
            return

        req = scheduler_pb.CancelBuildRequest(build_id=self.build_id)
        try:
            response = self.exec.CancelBuild(req)
            if response.status != common_pb.BuildStatus.BUILD_CANCELLED:
                log.warning("Failed to cancel build: {}", response.status)
        except grpc.RpcError as rpc_error:
            log.warning("Failed to cancel build: {}", rpc_error.details())
        finally:
            self.aborted = True

    def create_executor(self, task):
        """ Create an executor for the given task. """
        return RemoteExecutor(self.factory, self, task)


@scheduler.ExecutorFactory.Register
class RemoteExecutionFactory(NetworkExecutorFactory):
    """
    Factory for remote executors.

    Registers a build session with the scheduler and creates task executors.
    """

    def __init__(self, options):
        workers = config.getint(NAME, "workers", 1000)
        super().__init__(max_workers=workers)
        self._options = options

    @property
    def options(self):
        return self._options

    def create_session(self, graph):
        """ Create a build session in the scheduler. """
        session = RemoteSession(self)
        session.initialize(graph)
        return session

    def create(self, session, task):
        """ Create an executor for the given task. """
        return session.create_executor(task)


log.verbose("[Remote] Loaded")


@cli.cli.command(hidden=True)
@click.option("-w", "--worker", required=True, help="Worker identifier.")
@click.option("-b", "--build", required=True, help="Build identifier to enlist for.")
@click.argument("request", required=True)
@click.pass_context
def executor(ctx, worker, build, request):
    address = config.geturi(NAME, "uri", "tcp://scheduler.:9090")
    raise_error_if(address.scheme not in ["tcp"], "Invalid scheme in scheduler URI config: {}", address.scheme)
    raise_error_if(not address.netloc, "Invalid network address in scheduler URI config: {}", address.netloc)

    channel = grpc.insecure_channel(address.netloc)
    log.verbose("Waiting for GRPC channel to connect")
    grpc.channel_ready_future(channel).result()
    log.verbose("GRPC channel established: {}", address.netloc)

    sched = worker_grpc.WorkerStub(channel)

    with open(request, "rb") as f:
        request = scheduler_pb.BuildRequest()
        request.ParseFromString(f.read())

    # Set log level
    loglevel = request.environment.loglevel
    log.set_level_pb(loglevel)

    # Import workspace
    loader.import_workspace(request.environment)

    # Import configuration snippet
    config.import_config(request.environment.config)

    # Import configuration parameters (-c params.key)
    config.import_params({param.key: param.value for param in request.environment.parameters})

    options = JoltOptions(
        network=True,
        local=False,
        download=config.getboolean("network", "download", True),
        upload=config.getboolean("network", "upload", True),
        keep_going=False,
        default=request.environment.task_default_parameters,
        worker=True,
        debug=False,
        salt=None,
        jobs=1)

    log.set_worker()
    log.verbose("Local build as a worker")

    tasks = loader.JoltLoader.get().load()
    for cls in tasks:
        TaskRegistry.get().add_task_class(cls)

    # Create the
    acache = cache.ArtifactCache.get(options)
    executors = ExecutorRegistry.get(options)
    strategy = WorkerStrategy(executors, acache)
    hooks.TaskHookRegistry.get(options)
    registry = TaskRegistry.get(options)

    for task in options.default:
        registry.set_default_parameters(task)

    # Build the graph of tasks
    gb = GraphBuilder(registry, acache, options=options, progress=True, buildenv=request.environment)
    task_names = [task.name for task in request.environment.tasks.values()]
    dag = gb.build(task_names)

    # Enlist to execute build tasks from the scheduler
    enlist_msg = scheduler_pb.TaskUpdate(
        request=scheduler_pb.TaskRequest(build_id=build),
        worker=scheduler_pb.WorkerAllocation(id=worker, hostname=utils.hostname()),
    )

    # A queue to send updates to the scheduler
    updates = Queue()
    updates.push(enlist_msg)

    try:
        log.info("Subscribing to tasks")

        # Subscribe to tasks
        for task in sched.GetTasks(updates):
            log.set_level_pb(loglevel)

            log.info("Queuing {}", task.task_id)
            graph_task = dag.get_task_by_identity(task.task_id)
            executor = None
            status = None

            try:
                session = {}

                # Create an executor for the task
                executor = strategy.create_executor(session, graph_task)

                # Run the task
                with log.handler(LogHandler(updates, task)):
                    executor.run(JoltEnvironment(cache=acache, queue=None, worker=True))

            except KeyboardInterrupt:
                # Send an update to the scheduler
                update = scheduler_pb.TaskUpdate(
                    request=task,
                    status=common_pb.TaskStatus.TASK_CANCELLED,
                )
                updates.push(update)
                continue

            except Exception:
                status = common_pb.TaskStatus.TASK_FAILED

            else:
                status = graph_task.status()

            finally:
                errors = []

                # If the task status remains queued, mark it as failed
                if status in [common_pb.TaskStatus.TASK_QUEUED]:
                    status = common_pb.TaskStatus.TASK_FAILED

                # Add errors from the task to the update sent to the scheduler
                with graph_task.task.report() as report:
                    for error in report.errors:
                        errors.append(common_pb.TaskError(
                            type=str(error.type),
                            location=str(error.location),
                            message=str(error.message),
                            details=str(error.details),
                        ))

                # Send an update to the scheduler
                update = scheduler_pb.TaskUpdate(
                    request=task,
                    status=status,
                    errors=errors,
                )
                updates.push(update)

                # Release references to cache artifacts
                acache.release()

    except grpc.RpcError as rpc_error:
        log.warning("Scheduler Error: {}", rpc_error.details())

    except KeyboardInterrupt:
        log.info("Interrupted, exiting")

    except Exception as e:
        log.set_level(log.EXCEPTION)
        log.exception(e)
        raise e

    log.info("Exiting")
