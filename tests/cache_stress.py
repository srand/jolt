#!/usr/bin/env python

import jolt
from jolt import cache
from jolt import expires
from jolt import log
from jolt import tools
from jolt import utils
from jolt import loader
from os import path

log.set_level(log.DEBUG)
log._stdout.setFormatter(log._file_formatter)
log._stderr.setFormatter(log._file_formatter)


loader.JoltLoader.get().set_workspace_path(path.join(path.dirname(__file__)))


tools = tools.Tools()
wsdir = tools.getcwd()
builddir = None


def LogEntryExit(func):
    @utils.wraps(func)
    def wrapper(*args, **kwargs):
        # log.info(f"Entering {func.__name__}")
        result = func(*args, **kwargs)
        # log.info(f"Exiting {func.__name__}")
        return result
    return wrapper


class MockStorageProviderFactory(cache.StorageProviderFactory):
    def __init__(self):
        super(MockStorageProviderFactory, self).__init__()
        self.storage_provider = None

    def create(self, config):
        if self.storage_provider is None:
            self.storage_provider = MockStorageProvider()
        return self.storage_provider


class MockStorageProvider(cache.StorageProvider):
    factory = MockStorageProviderFactory()

    def download(self, artifact, force=False):
        global builddir
        tools.archive(builddir, artifact.get_archive_path())



cache.ArtifactCache.storage_provider_factories = [
    MockStorageProvider.factory,
]

the_cache = cache.ArtifactCache()
the_tasks = []



for i in range(1):
    class Task(object):
        name = f"{i}"
        joltdir = wsdir

        def __init__(self) -> None:
            self.canonical_name = self.name
            self.expires = expires.Immediately()
            self.influence = []
            self.requires = []
            self.task = self
            self.tools = tools
            self.short_qualified_name = self.name
            self.log_name = f"({self.name} {self.identity[:8]})"
            self.artifact = the_cache.get_artifact(self, "main")
            self.info = log.info
            self.debug = log.debug

        def _get_parameters(self):
            return {}

        def _get_parameter_objects(self):
            return {}

        def is_cacheable(self):
            return True

        def unpack(self, artifact, tools):
            pass

        @property
        def identity(self):
            return utils.hashstring(self.name)

    the_tasks.append(Task())


@LogEntryExit
def commit(task, discard=True):
    with the_cache.lock_artifact(task.artifact, discard=discard):
        with tools.cwd(builddir):
            task.artifact.collect("*.txt")
        the_cache.commit(task.artifact)
    the_cache.release()


@LogEntryExit
def discard(task):
    if the_cache.is_available_locally(task.artifact):
        the_cache.discard(task.artifact)
        the_cache.release()


@LogEntryExit
def download(task, discard=True):
    if not the_cache.is_available_locally(task.artifact):
        the_cache.download(task.artifact, force=discard)
        the_cache.release()


@LogEntryExit
def unpack(task):
    if the_cache.is_available_locally(task.artifact):
        the_cache.unpack(task.artifact)
        the_cache.release()


@LogEntryExit
def release():
    the_cache.release()


def main():
    global builddir
    builddir = tools.builddir()

    # with tools.cwd(builddir):
    #     for i in range(100):
    #         tools.write_file(f"file{i}.txt", f"Hello, {i}!")

    while True:
        for task in the_tasks:
            commit(task)
            unpack(task)
            discard(task)
            download(task)


if __name__ == '__main__':
    try:
        with tools:
            main()
    except KeyboardInterrupt:
        log.info("Exiting...")
