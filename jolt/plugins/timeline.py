from datetime import datetime
import os

from jolt import log
from jolt import tools
from jolt import utils
from jolt.hooks import TaskHook, TaskHookFactory
from jolt import config


NAME_LOG = "Timeline"


class TimelineHooks(TaskHook):
    def __init__(self):
        self.path = os.path.join(
            config.get_workdir(),
            config.get("timeline", "path", "timeline.html")
        )
        self.tasks = []
        self.task_ids = {}
        self.tools = tools.Tools()

    def started(self, task):
        task._timeline_started = datetime.now().isoformat()
        self.task_ids[task] = len(self.tasks)

    def finished(self, task):
        task._timeline_finished = datetime.now().isoformat()
        self.tasks.append(task)
        self.render()

    def render(self):
        timeline = utils.render(
            "timeline.html.template",
            deps=self.deps,
            enumerate=enumerate,
            tasks=self.tasks)

        self.tools.write_file(self.path, timeline, expand=False)

    def deps(self, task):
        ids = []
        for anc in task.descendants:
            if anc in self.task_ids:
                ids.append(str(self.task_ids[anc]))
        return "null" if not ids else "'" + ",".join(ids) + "'"

    def task_started_download(self, task):
        self.started(task)

    def task_started_execution(self, task):
        self.started(task)

    def task_started_upload(self, task):
        self.started(task)

    def task_finished_download(self, task):
        self.finished(task)

    def task_finished_upload(self, task):
        self.finished(task)

    def task_finished_execution(self, task):
        self.finished(task)


@TaskHookFactory.register
class TimelineFactory(TaskHookFactory):
    def create(self, env):
        log.verbose(NAME_LOG + " Loaded")
        return TimelineHooks()
