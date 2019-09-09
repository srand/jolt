from datetime import datetime

from jolt import *
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.error import raise_error_if
from jolt.hooks import TaskHook, TaskHookFactory


log.verbose("[LogStash] Loaded")


class LogStashHooks(TaskHook):
    def __init__(self):
        self._uri = config.get("logstash", "http.uri")
        self._failed_enabled = config.get("logstash", "failed", False)
        self._finished_enabled = config.get("logstash", "finished", False)
        raise_error_if(not self._uri, "logstash.http.uri not configured")

    def _get_uri(self, task):
        return "{}/{}-{}.txt".format(
            self._uri,
            datetime.now().strftime("%Y-%m-%d_%H%M%S.%f"),
            task.canonical_name)

    def _stash_log(self, task):
        with task.tools.tmpdir("logstash") as t:
            filepath = fs.path.join(t.path, "log")
            with open(filepath, "w") as f:
                f.write(task.logsink_buffer.getvalue())
            task.tools.upload(filepath, self._get_uri(task))

    def task_started(self, task):
        task.logsink = log.threadsink()
        task.logsink_buffer = task.logsink.__enter__()

    def task_failed(self, task):
        task.logsink.__exit__(None, None, None)
        if self._failed_enabled:
            self._stash_log(task)

    def task_finished(self, task):
        task.logsink.__exit__(None, None, None)
        if self._finished_enabled:
            self._stash_log(task)


@TaskHookFactory.register
class LogStashFactory(TaskHookFactory):
    def create(self, env):
        return LogStashHooks()
