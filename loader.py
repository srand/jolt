import inspect
import imp
from tasks import Task, Test
import copy
import glob
import filesystem as fs
import log
import utils
import os


@utils.Singleton
class JoltLoader(object):
    filename = "*.jolt"

    def __init__(self):
        self._tasks = []
        self._tests = []
        self._source = []
        self._path = None

    def _load_file(self, path):
        classes = []

        directory = fs.path.dirname(path)
        name, ext = fs.path.splitext(fs.path.basename(path))

        with open(path) as f:
            self._source.append(f.read())

        module = imp.load_source("joltfile_{0}".format(name), path)
        for name in module.__dict__:
            obj = module.__dict__[name]
            if inspect.isclass(obj):
                classes.append(obj)

        tasks = [cls for cls in classes if issubclass(cls, Task) and cls is not Task]
        for task in tasks:
            task.name = task.name or task.__name__.lower()
            task.joltdir = directory
        self._tasks += tasks

        tests = [cls for cls in classes if issubclass(cls, Test) and cls is not Test]
        for test in tests:
            test.name = test.name or test.__name__.lower()
            test.joltdir = directory
        self._tests += tests

        log.verbose("Loaded: {0}", path)

        return tasks

    def load(self, recursive=False):
        files = []
        path = os.getcwd()
        root = fs.path.normpath("/")
        while not files:
            files = glob.glob(fs.path.join(path, JoltLoader.filename))
            for file in files:
                self._load_file(file)
            path = fs.path.dirname(path)
            if path == root:
                break
        return self._tasks, self._tests

    def get_sources(self):
        return "".join(self._source)
