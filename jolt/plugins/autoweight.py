from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.hooks import TaskHook, TaskHookFactory


log.verbose("[AutoWeight] Loaded")


class WeightHooks(TaskHook):
    def __init__(self):
        self._tasks = {}
        self._samples = config.getint("autoweight", "samples", 10)
        self.load()

    @property
    def dbpath(self):
        return fs.path.join(config.get_cachedir(), "autoweight.json")

    def load(self):
        self._tasks = utils.fromjson(self.dbpath, ignore_errors=True)

    def save(self):
        utils.tojson(self.dbpath, self._tasks, ignore_errors=True)

    def task_created(self, task):
        data = self._tasks.get(task.qualified_name)
        if data:
            task.weight = max(data)

    def task_finished(self, task):
        data = self._tasks.get(task.qualified_name)
        if data:
            data.append(task.duration_running.seconds)
            self._tasks[task.qualified_name] = data[-self._samples:]
        else:
            self._tasks[task.qualified_name] = [task.duration_running.seconds]
        self.save()


@TaskHookFactory.register
class WeightFactory(TaskHookFactory):
    def create(self, env):
        return WeightHooks()
