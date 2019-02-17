import inspect
import imp
import copy
import glob
import os
import base64

from jolt.tasks import Task, Test, Resource
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt import scheduler
from jolt.plugins.ninja import CXXExecutable, CXXLibrary
from jolt.manifest import *


@utils.Singleton
class JoltLoader(object):
    filename = "*.jolt"

    def __init__(self):
        self._tasks = []
        self._tests = []
        self._source = {}
        self._path = None

    def _load_file(self, path):
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

        cls_exclude_list = [Task, Resource, CXXLibrary, CXXExecutable]

        tasks = [cls for cls in classes
                 if issubclass(cls, Task) and cls not in cls_exclude_list \
                 and not cls.__name__.startswith("_")]
        for task in tasks:
            task.name = task.name or task.__name__.lower()
            task.joltdir = directory
        self._tasks += tasks

        tests = [cls for cls in classes if issubclass(cls, Test) and cls is not Test \
                 and not cls.__name__.startswith("_")]
        for test in tests:
            test.name = test.name or test.__name__.lower()
            test.joltdir = directory
        self._tests += tests

        log.verbose("Loaded: {0}", path)

        return tasks

    def _load_files(self):
        files = []
        path = os.getcwd()
        root = fs.path.normpath("/")
        while not files:
            files = glob.glob(fs.path.join(path, JoltLoader.filename))
            for file in files:
                self._load_file(file)
            if files:
                self._path = path
                break
            path = fs.path.dirname(path)
            if path == root:
                break
        return self._tasks, self._tests

    def _load_manifest(self, manifest):
        for recipe in manifest.recipes:
            with open(recipe.path, "w") as f:
                f.write(base64.decodestring(recipe.source.encode()).decode())
            self._load_file(fs.path.join(os.getcwd(), recipe.path))
        if self._path is None:
            self._path = os.getcwd()

    def load(self, manifest=None):
        self._load_files()
        if manifest is not None:
            self._load_manifest(manifest)
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

ManifestExtensionRegistry.add(RecipeExtension())
