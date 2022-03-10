
from jolt import cache
from jolt import config
from jolt import filesystem as fs
from jolt import loader
from jolt import log
from jolt import utils
from jolt.error import raise_error_if
from jolt.hooks import TaskHook, TaskHookFactory


log.verbose("[Symlinks] Loaded")


class SymlinkHooks(TaskHook):
    def __init__(self):
        self._path = config.get("symlinks", "path", "artifacts")
        raise_error_if(not self._path, "symlinks.path not configured")

    def task_finished(self, task):
        if not task.has_artifact():
            return

        srcpath = cache.ArtifactCache.get().get_path(task)
        destpath = fs.path.join(
            loader.get_workspacedir(),
            self._path,
            utils.canonical(task.short_qualified_name))

        if fs.path.exists(srcpath):
            fs.unlink(destpath, ignore_errors=True)
            fs.makedirs(fs.path.dirname(destpath))
            fs.symlink(srcpath, destpath)

    def task_pruned(self, task):
        self.task_finished(task)

    def task_skipped(self, task):
        self.task_finished(task)


@TaskHookFactory.register
class SymlinkFactory(TaskHookFactory):
    def create(self, env):
        return SymlinkHooks()
