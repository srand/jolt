import glob
import os
import yaml

from jolt.tasks import Task
from jolt import log
from jolt import loader
from jolt.error import raise_error_if
from jolt import influence


log.verbose("[YamlTask] Loaded")


@influence.attribute("yaml")
class YamlTask(Task):
    name = None
    requires = []
    cacheable = True
    commands = []
    collects = []
    extends = ""
    fast = False
    influence = []
    joltdir = "."
    joltproject = None
    metadata = {}
    selfsustained = False
    taint = False
    weight = False
    yaml = None

    def run(self, d, t):
        self.builddir = t.builddir()
        with t.cwd(self.builddir):
            for cmd in self.commands:
                t.run(cmd)

    def publish(self, a, t):
        with t.cwd(self.builddir):
            for pf in self.collects:
                a.collect(**pf)
            for section, item in self.metadata.items():
                for key, value in item.items():
                    setattr(getattr(a, section), key, value)


class YamlTaskBuilder(object):
    def build(self, yobj):
        return None


_builders = {}


def register(cls):
    raise_error_if(not issubclass(cls, YamlTaskBuilder),
                   "{} is not a YamlTaskBuilder", cls.__name__)
    _builders[cls.name] = cls()


@register
class RegularYamlTaskBuilder(YamlTaskBuilder):
    name = "task"

    def build(self, ytask):
        class LoadedYamlTask(YamlTask):
            name = None
            requires = []
            cacheable = True
            commands = []
            collects = []
            cxxinfo = []
            exports = []
            extends = ""
            fast = False
            influence = []
            joltdir = "."
            joltproject = None
            selfsustained = False
            taint = False
            weight = False
            yaml = None

        for key, obj in ytask.items():
            setattr(LoadedYamlTask, key, obj)

        LoadedYamlTask.yaml = ytask

        return LoadedYamlTask


class YamlRecipe(loader.Recipe):
    def __init__(self, *args, **kwargs):
        super(YamlRecipe, self).__init__(*args, **kwargs)
        self._preload()

    def _preload(self):
        with open(self.path) as f:
            root = yaml.safe_load_all(f)
            root = [o for o in root]

        for doc in root:
            for key, obj in doc.items():
                builder = _builders.get(key)
                if not builder:
                    log.verbose("Unknown yaml task type: {}", key)
                    continue
                task = builder.build(obj)
                task.joltdir = os.path.dirname(self.path)
                self.tasks.append(task)

    def is_valid(self):
        return len(self.tasks) > 0


class YamlLoader(loader.Loader):
    def __init__(self):
        self._recipes = []
        self._find_files()

    def _find_files(self):
        files = []
        oldpath = None
        curpath = os.getcwd()
        while not self._recipes and oldpath != curpath:
            files = glob.glob(os.path.join(curpath, "*.yaml"))

            for filepath in files:
                recipe = YamlRecipe(filepath)
                if recipe.is_valid():
                    self._recipes.append(recipe)

            oldpath = curpath
            curpath = os.path.dirname(oldpath)
        self.path = oldpath

    @property
    def recipes(self):
        return self._recipes


@loader.register
class YamlLoaderFactory(loader.LoaderFactory):
    def create(self):
        return YamlLoader()
