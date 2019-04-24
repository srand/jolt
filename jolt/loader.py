import inspect
import imp
import glob
import os
import base64

from jolt.tasks import Task, TaskGenerator, Test
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.manifest import ManifestExtension
from jolt.manifest import ManifestExtensionRegistry


@utils.Singleton
class JoltLoader(object):
    filename = "*.jolt"

    def __init__(self):
        self._tasks = []
        self._tests = []
        self._source = {}
        self._path = None

    def _load_file(self, path, joltdir=None):
        classes = []

        directory = fs.path.dirname(path)
        name, ext = fs.path.splitext(fs.path.basename(path))

        with open(path) as f:
            self._source[path] = f.read()

        module = imp.load_source("joltfile_{0}".format(name), path)
        for name in module.__dict__:
            obj = module.__dict__[name]
            if inspect.isclass(obj):
                classes.append(obj)

        def is_abstract(cls):
            return cls.__dict__.get("abstract", False)

        generators = [cls for cls in classes
                      if issubclass(cls, TaskGenerator) \
                      and not cls.__name__.startswith("_") \
                      and not is_abstract(cls)]
        for gen in generators:
            classes = utils.as_list(gen().generate()) + classes

        tasks = [cls for cls in classes
                 if issubclass(cls, Task) \
                 and not cls.__name__.startswith("_") \
                 and not is_abstract(cls)]
        for task in tasks:
            task.name = task.name or task.__name__.lower()
            task.joltdir = joltdir or directory
        self._tasks += tasks

        tests = [cls for cls in classes if issubclass(cls, Test) \
                 and not cls.__name__.startswith("_") \
                 and not is_abstract(cls)]
        for test in tests:
            test.name = test.name or test.__name__.lower()
            test.joltdir = joltdir or directory
        self._tests += tests

        log.verbose("Loaded: {0}", path)

        return tasks

    def _load_files(self):
        files = []
        path = os.getcwd()
        while not files:
            files = glob.glob(fs.path.join(path, JoltLoader.filename))
            for file in files:
                self._load_file(file)
            if files:
                self._path = path
                break
            opath = path
            path = fs.path.dirname(path)
            if path == opath:
                break
        return self._tasks, self._tests

    def load(self, manifest=None):
        self._load_files()
        return self._tasks, self._tests

    def get_sources(self):
        return self._source.items()

    @property
    def joltdir(self):
        return self._path


class RecipeExtension(ManifestExtension):
    def export_manifest(self, manifest, task):
        loader = JoltLoader.get()
        for path, source in loader.get_sources():
            manifest_recipe = manifest.create_recipe()
            manifest_recipe.path = fs.path.basename(path)
            manifest_recipe.source = base64.encodestring(source.encode()).decode()

    def import_manifest(self, manifest):
        for recipe in manifest.recipes:
            with open(recipe.path, "w") as f:
                f.write(base64.decodestring(recipe.source.encode()).decode())


ManifestExtensionRegistry.add(RecipeExtension())
