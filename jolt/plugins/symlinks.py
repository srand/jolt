
from jolt import config
from jolt import filesystem as fs
from jolt import loader
from jolt import log
from jolt import utils
from jolt.error import raise_error_if
from jolt.hooks import CliHook, CliHookFactory
from jolt.hooks import TaskHook, TaskHookFactory

from contextlib import contextmanager

log.verbose("[Symlinks] Loaded")


class SymlinkTaskHooks(TaskHook):
    def __init__(self):
        self._path = config.get("symlinks", "path", "artifacts")
        raise_error_if(not self._path, "symlinks.path not configured")

    @property
    def rootpath(self):
        return fs.path.normpath(
            fs.path.join(
                fs.path.dirname(loader.JoltLoader.get().build_path),
                self._path
            )
        )

    def task_finished(self, task):
        if not task.has_artifact():
            return

        for artifact in task.artifacts:
            srcpath = artifact.final_path
            if artifact.name == "main":
                destpath = fs.path.join(
                    self.rootpath,
                    utils.canonical(task.short_qualified_name),
                )
            else:
                destpath = fs.path.join(
                    self.rootpath,
                    artifact.name + "@" + utils.canonical(task.short_qualified_name),
                )

            if fs.path.exists(srcpath):
                fs.unlink(destpath, ignore_errors=True)
                fs.makedirs(fs.path.dirname(destpath))
                fs.symlink(srcpath, destpath)

    def task_pruned(self, task):
        self.task_finished(task)

    def task_skipped(self, task):
        self.task_finished(task)


class SymlinkCliHooks(CliHook):
    def __init__(self):
        self._path = config.get("symlinks", "path", "artifacts")
        raise_error_if(not self._path, "symlinks.path not configured")

    @contextmanager
    def cli_clean(self, *args, **kwargs):
        yield
        try:
            path = fs.path.join(loader.get_workspacedir(), self._path)
            fs.rmtree(path, onerror=fs.onerror_warning)
        except (AssertionError, FileNotFoundError):
            pass


@TaskHookFactory.register
class SymlinkTaskHookFactory(TaskHookFactory):
    def create(self, env):
        return SymlinkTaskHooks()


@CliHookFactory.register
class SymlinkCliHookFactory(CliHookFactory):
    def create(self, env):
        return SymlinkCliHooks()
