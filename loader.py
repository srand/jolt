import inspect
import imp
from tasks import Task
import copy
import glob
import filesystem as fs
import log
import utils


@utils.Singleton
class JoltLoader(object):
    filename = "*.jolt"
    
    def __init__(self):
        self._tasks = []
        self._source = []

    def load_file(self, path):
        classes = []

        name, ext = fs.path.splitext(fs.path.basename(path))

        with open(path) as f:
            self._source.append(f.read())
        
        module = imp.load_source("joltfile_{}".format(name), path)
        for name in module.__dict__:
            if inspect.isclass(module.__dict__[name]):
                classes.append(module.__dict__[name])

        tasks = [cls for cls in classes if issubclass(cls, Task)]
        self._tasks += tasks

        log.verbose("Loaded: {}", path)
        
        return tasks

    def load_directory(self, path=".", recursive=False):
        files = glob.glob(fs.path.join(path, JoltLoader.filename))
        for file in files:
            self.load_file(file)
        return self._tasks

    def get_sources(self):
        return "".join(self._source)
