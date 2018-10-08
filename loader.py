import inspect
import imp
from tasks import Task
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
        self._source = []

    def _load_file(self, path):
        classes = []

        name, ext = fs.path.splitext(fs.path.basename(path))

        with open(path) as f:
            self._source.append(f.read())
        
        module = imp.load_source("joltfile_{}".format(name), path)
        for name in module.__dict__:
            if inspect.isclass(module.__dict__[name]):
                classes.append(module.__dict__[name])

        tasks = [cls for cls in classes if issubclass(cls, Task) and cls is not Task]
        self._tasks += tasks

        log.verbose("Loaded: {}", path)
        
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
        return self._tasks

    
    
    def get_sources(self):
        return "".join(self._source)
