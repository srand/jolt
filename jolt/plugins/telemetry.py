from requests.exceptions import RequestException
from requests.api import post

from jolt import config
from jolt import log
from jolt import utils
from jolt.error import raise_error_if
from jolt.hooks import TaskHook, TaskHookFactory


log.verbose("[Telemetry] Loaded")


class TelemetryHooks(TaskHook):
    def __init__(
            self,
            plugin="telemetry",
            uri=None,
            local=True,
            network=True,
            queued=True,
            started=True,
            failed=True,
            finished=True):
        self._uri = uri or config.get(plugin, "uri", uri)
        self._network = config.getboolean(plugin, "network", network)
        self._local = config.getboolean(plugin, "local", local)
        self._queued = config.getboolean(plugin, "queued", queued)
        self._started = config.getboolean(plugin, "started", started)
        self._failed = config.getboolean(plugin, "failed", failed)
        self._finished = config.getboolean(plugin, "finished", finished)
        raise_error_if(not self._uri, "telemetry.uri not configured")

    @utils.retried.on_exception((RequestException))
    def post(self, task, event, client):
        data = {
            "name": task.short_qualified_name,
            "identity": task.identity,
            "instance": task.task._instance.value,
            "hostname": utils.hostname(),
            "role": "client" if client else "worker",
            "event": event,
            "routing_key": getattr(task.task, "routing_key", "default")
        }
        if hasattr(task, "logstash"):
            data["log"] = task.logstash

        r = post(self._uri, json=data)
        r.raise_for_status()

    def task_started(self, task):
        if task.is_remotely_executed():
            if self._network and self._queued:
                self.post(task, "queued", client=True)
        elif task.is_locally_executed():
            if self._local and not task.options.worker:
                if self._queued:
                    self.post(task, "queued", client=True)
                if self._started:
                    self.post(task, "started", client=True)
            if self._network and task.options.worker:
                if self._started:
                    self.post(task, "started", client=False)

    def task_failed(self, task):
        if not self._failed:
            return
        if task.is_locally_executed():
            if self._local and not task.options.worker:
                self.post(task, "failed", client=True)
            if self._network and task.options.worker:
                self.post(task, "failed", client=False)
        if task.is_remotely_executed():
            if self._network and self._failed:
                self.post(task, "failed", client=True)

    def task_unstable(self, task):
        self.task_failed(task)

    def task_finished(self, task):
        if not self._finished:
            return
        if task.is_locally_executed():
            if self._local and not task.options.worker:
                self.post(task, "finished", client=True)
            if self._network and task.options.worker:
                self.post(task, "finished", client=False)
        if task.is_remotely_executed():
            if self._network and self._finished:
                self.post(task, "finished", client=True)


# After logstash
@TaskHookFactory.register_with_prio(20)
class TelemetryFactory(TaskHookFactory):
    def create(self, env):
        if "telemetry" in config.plugins():
            return TelemetryHooks()
        return None
