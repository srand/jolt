from contextlib import contextmanager
from datetime import datetime

from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt.error import raise_error_if
from jolt.hooks import TaskHook, TaskHookFactory


log.verbose("[LogStash] Loaded")


class LogStashHooks(TaskHook):
    def __init__(self):
        self._uri = config.get("logstash", "http.uri", "http://logstash")
        self._failed_enabled = config.getboolean("logstash", "failed", False)
        self._finished_enabled = config.getboolean("logstash", "passed", config.getboolean("logstash", "finished", False))
        raise_error_if(not self._uri, "logstash.http.uri not configured")

    def _get_uri(self, task):
        return "{}/{}-{}.txt".format(
            self._uri,
            datetime.now().strftime("%Y-%m-%d_%H%M%S.%f"),
            task.canonical_name)

    def _stash_log(self, task, logbuffer):
        with task.tools.tmpdir("logstash") as tmp:
            filepath = fs.path.join(tmp, "log")
            with open(filepath, "w") as f:
                f.write(logbuffer)
            task.logstash = self._get_uri(task)
            task.tools.upload(filepath, task.logstash, exceptions=False)

    @contextmanager
    def task_run(self, task):
        with log.threadsink() as logsink:
            try:
                yield
            except Exception as e:
                if self._failed_enabled:
                    self._stash_log(task, logsink.getvalue())
                raise e
            else:
                if self._finished_enabled:
                    self._stash_log(task, logsink.getvalue())


# Must run before other plugins which depend on the
# logstash_uri TaskProxy attribute.
@TaskHookFactory.register_with_prio(10)
class LogStashFactory(TaskHookFactory):
    def create(self, env):
        return LogStashHooks()
