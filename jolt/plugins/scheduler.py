import click
import grpc
import queue
from threading import Lock

from google.protobuf.timestamp_pb2 import Timestamp

from jolt import cache
from jolt import cli
from jolt import colors
from jolt import config
from jolt import hooks
from jolt import loader
from jolt import log
from jolt import manifest
from jolt import common_pb2 as common_pb
from jolt import scheduler
from jolt import utils
from jolt.error import JoltError, raise_error, raise_task_error, raise_task_error_if
from jolt.graph import GraphBuilder
from jolt.scheduler import ExecutorRegistry, JoltEnvironment, NetworkExecutor, NetworkExecutorFactory, WorkerStrategy
from jolt.tasks import TaskRegistry
from jolt.options import JoltOptions
from jolt.plugins import selfdeploy
from jolt.plugins.remote_execution import scheduler_pb2 as scheduler_pb
from jolt.plugins.remote_execution import scheduler_pb2_grpc as scheduler_grpc
from jolt.plugins.remote_execution import worker_pb2_grpc as worker_grpc


NAME = "scheduler"
TYPE = "Remote execution"


def locked(func):
    def _f(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
    return _f


class LogHandler(object):
    def __init__(self, queue, task):
        self.queue = queue
        self.task = task
        self.level = log.EXCEPTION

    def emit(self, record):
        pass

    def handle(self, record):
        try:
            record.message = record.msg.format(*record.args)
        except Exception:
            record.message = record.msg

        timestamp = Timestamp()
        timestamp.FromMilliseconds(int(record.created * 1000))

        self.queue.push(
            scheduler_pb.TaskUpdate(
                request=self.task,
                status=common_pb.TaskStatus.TASK_RUNNING,
                loglines=[
                    common_pb.LogLine(
                        context=self.task.task_id[:8],
                        level=record.levelno,
                        time=timestamp,
                        message=record.message,
                    ),
                ]
            )
        )

    def createLock(self):
        return None


class TaskCancelledException(JoltError):
    pass


class Queue(object):
    def __init__(self):
        self.q = queue.Queue()

    def __next__(self):
        data = self.q.get()
        return data

    def push(self, item):
        self.q.put(item)


class RemoteExecutor(NetworkExecutor):
    def __init__(self, factory, session, task):
        self.factory = factory
        self.session = session
        self.task = task

    def cancel(self):
        self.session.cancel()

    def download_persistent_artifacts(self, task):
        if not task.has_artifact():
            return
        if not task.cache.download_enabled():
            return
        if not task.is_downloadable():
            return
        raise_task_error_if(
            not task.download(persistent_only=True), task,
            "Failed to download artifact")
        for extension in task.extensions:
            self.download_persistent_artifacts(extension)

    def download_session_artifacts(self, task):
        if not task.has_artifact():
            return
        if not task.cache.download_enabled():
            return
        if not task.is_downloadable():
            return
        if not task.download(session_only=True):
            task.warning("Failed to download session artifact")
        for extension in task.extensions:
            self.download_persistent_artifacts(extension)

    def run(self, env):
        try:
            self.run_build(env)
        except grpc.RpcError as rpc_error:
            raise_task_error(self.task, "Scheduler error: {}", rpc_error.details())

    @utils.retried.on_exception(grpc.RpcError)
    def run_build(self, env):
        try:
            self.session.make_build_request()

            self.task.queued(remote=True)
            for extension in self.task.extensions:
                extension.queued(remote=True)

            request = scheduler_pb.TaskRequest(
                build_id=self.session.build.build_id,
                task_id=self.task.identity,
            )
            response = self.session.exec.ScheduleTask(request)

            with hooks.task_run([self.task] + self.task.extensions):
                self.run_task(env, response)

            self.download_persistent_artifacts(self.task)

            self.task.finished_execution(remote=True)
            for extension in self.task.extensions:
                extension.finished_execution(remote=True)

        except TaskCancelledException:
            pass

        except grpc.RpcError as rpc_error:
            log.warning("Scheduler error: {}", rpc_error.details())
            self.session.clear_build_request()
            raise rpc_error

        except Exception as e:
            log.exception()
            self.task.failed_execution(remote=True)
            for extension in self.task.extensions:
                extension.failed_execution(remote=True)
            if not self.task.is_unstable:
                raise e

        finally:
            self.download_session_artifacts(self.task)

    def run_task(self, env, response):
        last_status = common_pb.TaskStatus.TASK_QUEUED

        for progress in response:
            for line in progress.loglines:
                log.log(
                    line.level,
                    line.message,
                    created=line.time.ToMicroseconds() / 1000000,
                    context=line.context[:7],
                    prefix=True)

            if progress.status in [common_pb.TaskStatus.TASK_RUNNING] \
               and progress.status != self.task.status():
                self.task.running_execution(remote=True)
                for extension in self.task.extensions:
                    extension.running_execution(remote=True)

            if progress.status in [
                    common_pb.TaskStatus.TASK_PASSED,
                    common_pb.TaskStatus.TASK_DOWNLOADED,
                    common_pb.TaskStatus.TASK_UPLOADED,
                    common_pb.TaskStatus.TASK_SKIPPED,
            ]:
                break

            if progress.status in [
                    common_pb.TaskStatus.TASK_CANCELLED,
                    common_pb.TaskStatus.TASK_FAILED,
                    common_pb.TaskStatus.TASK_UNSTABLE,
            ]:
                if last_status in [common_pb.TaskStatus.TASK_QUEUED]:
                    raise TaskCancelledException()

                for error in progress.errors:
                    with self.task.task.report() as report:
                        report.add_error(
                            error.type,
                            error.location,
                            error.message,
                            error.details,
                        )
                with self.task.task.report() as report:
                    for error in report.errors:
                        raise_error(error.message)
                raise raise_error("Remote execution failed")

            if progress.status in [
                    common_pb.TaskStatus.TASK_ERROR,
            ]:
                for error in progress.errors:
                    with self.task.task.report() as report:
                        report.add_error(
                            error.type,
                            error.location,
                            error.message,
                            error.details,
                        )
                with self.task.task.report() as report:
                    for error in report.errors:
                        for line in error.details.splitlines():
                            log.error(line)
                        raise_error(f"{error.type}: {error.message}")
                raise raise_error("Remote execution failed")

            last_status = progress.status


class RemoteSession(object):
    def __init__(self, factory):
        self.factory = factory
        self.address = "{}:{}".format(
            config.get(NAME, "host", "jolt-scheduler"),
            config.getint(NAME, "port", 9090),
        )
        self.channel = grpc.insecure_channel(
            target=self.address,
        )
        self.exec = scheduler_grpc.SchedulerStub(self.channel)
        self.build = None
        self.aborted = False
        self.lock = Lock()

    def initialize(self, graph):
        registry = ExecutorRegistry.get()

        parameters = []
        for key, value in registry.get_network_parameters(None).items():
            parameters.append(common_pb.Property(key=key, value=value))

        self.buildenv = common_pb.BuildEnvironment(
            client=selfdeploy.get_client(),
            parameters=parameters,
            task_default_parameters=scheduler.export_task_default_params(graph.tasks),
            tasks=scheduler.export_tasks(graph.tasks),
            workspace=loader.export_workspace(graph.tasks),
            loglevel=log.get_level(),
        )

    @locked
    def make_build_request(self):
        if self.build:
            return

        req = scheduler_pb.BuildRequest(environment=self.buildenv)
        self.build = self.exec.ScheduleBuild(req)

        log.info(colors.blue("Build registered with scheduler, waiting for worker"))
        return self.build

    def clear_build_request(self):
        self.build = None

    def cancel(self):
        if self.aborted:
            return

        if not self.build:
            self.aborted = True
            return

        req = scheduler_pb.CancelBuildRequest(build_id=self.build.build_id)
        try:
            response = self.exec.CancelBuild(req)
            if response.status != common_pb.BuildStatus.BUILD_CANCELLED:
                log.warning("Failed to cancel build: {}", response.status)
        except grpc.RpcError as rpc_error:
            log.warning("Failed to cancel build: {}", rpc_error.details())
        finally:
            self.aborted = True

    def create_executor(self, task):
        return RemoteExecutor(self.factory, self, task)


@scheduler.ExecutorFactory.Register
class RemoteExecutionFactory(NetworkExecutorFactory):
    def __init__(self, options):
        workers = config.getint(NAME, "workers", 1000)
        super().__init__(max_workers=workers)
        self._options = options

    @property
    def options(self):
        return self._options

    def create_session(self, graph):
        session = RemoteSession(self)
        session.initialize(graph)
        return session

    def create(self, session, task):
        return session.create_executor(task)


log.verbose("[Remote] Loaded")


@cli.cli.command()
@click.option("-w", "--worker", required=True, help="Worker identifier.")
@click.option("-b", "--build", required=True, help="Build identifier to enlist for.")
@click.argument("request", required=True)
@click.pass_context
def executor(ctx, worker, build, request):
    address = "{}:{}".format(
        config.get(NAME, "host", "scheduler."),
        config.getint(NAME, "port", 9090),
    )

    channel = grpc.insecure_channel(address)
    log.verbose("Waiting for GRPC channel to connect")
    grpc.channel_ready_future(channel).result()
    log.verbose("GRPC channel established")

    sched = worker_grpc.WorkerStub(channel)

    with open(request, "rb") as f:
        request = scheduler_pb.BuildRequest()
        request.ParseFromString(f.read())

    loglevel = request.environment.loglevel
    log.set_level(loglevel)

    manifest.ManifestExtensionRegistry.import_protobuf(request.environment)

    options = JoltOptions(
        network=False,
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

    acache = cache.ArtifactCache.get(options)
    executors = ExecutorRegistry.get(options)
    strategy = WorkerStrategy(executors, acache)
    hooks.TaskHookRegistry.get(options)
    registry = TaskRegistry.get(options)

    for task in options.default:
        registry.set_default_parameters(task)

    gb = GraphBuilder(registry, acache, options=options, progress=True, buildenv=request.environment)
    dag = gb.build(request.environment.tasks.keys())

    enlist_msg = scheduler_pb.TaskUpdate(
        build_id=build,
        worker_id=worker,
    )

    updates = Queue()
    updates.push(enlist_msg)

    try:
        log.info("Subscribing to tasks")

        for task in sched.GetTasks(updates):
            log.set_level(loglevel)

            log.info("Queuing {}", task.task_id)
            graph_task = dag.get_task_by_identity(task.task_id)

            for resource in filter(lambda task: task.is_resource() and not task.is_completed(), reversed(graph_task.children)):
                session = {}
                executor = strategy.create_executor(session, resource)
                executor.run(JoltEnvironment(cache=acache))

            executor = None
            try:
                session = {}
                executor = strategy.create_executor(session, graph_task)

                with log.handler(LogHandler(updates, task)):
                    executor.run(JoltEnvironment(cache=acache))

            except Exception as e:
                log.set_level(log.EXCEPTION)
                log.exception(e)

                errors = []
                with graph_task.task.report() as report:
                    for error in report.errors:
                        errors.append(common_pb.TaskError(
                            type=str(error.type),
                            location=str(error.location),
                            message=str(error.message),
                            details=str(error.details),
                        ))
                update = scheduler_pb.TaskUpdate(
                    request=task,
                    status=graph_task.status() or common_pb.TaskStatus.TASK_FAILED,
                    errors=errors,
                )
                updates.push(update)

            else:
                update = scheduler_pb.TaskUpdate(
                    request=task,
                    status=graph_task.status(),
                )
                updates.push(update)

    except Exception as e:
        log.set_level(log.EXCEPTION)
        log.exception(e)
        raise e

    log.info("Exiting")
