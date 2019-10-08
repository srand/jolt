import base64
import glob
import imp
import inspect
import os
import sys

from jolt.tasks import Alias, Task, TaskGenerator, TaskRegistry, Test, WorkspaceResource
from jolt.error import raise_task_error_if
from jolt import config
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
        self._project_recipes = {}
        self._project_resources = {}

    def _load_file(self, path, joltdir=None, joltproject=None):
        classes = []

        directory = fs.path.dirname(path)
        name, ext = fs.path.splitext(fs.path.basename(path))

        if not joltproject:
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
            task.joltproject = joltproject
        self._tasks += tasks

        tests = [cls for cls in classes if issubclass(cls, Test) \
                 and not cls.__name__.startswith("_") \
                 and not is_abstract(cls)]
        for test in tests:
            test.name = test.name or test.__name__.lower()
            test.joltdir = joltdir or directory
            test.joltproject = joltproject
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

    def _add_project_recipe(self, project, joltdir, src):
        recipes = self._project_recipes.get(project, [])
        recipes.append((joltdir, src))
        self._project_recipes[project] = recipes

    def _get_project_recipes(self, project):
        return self._project_recipes.get(project, [])

    def _add_project_resource(self, project, resource_name, resource_task):
        class ProjectResource(Alias):
            name =  project + "/" + resource_name
            requires = [resource_task]
        self._tasks.append(ProjectResource)
        resources = self._project_resources.get(project, [])
        resources.append((resource_name, resource_task))
        self._project_resources[project] = resources

    def _get_project_resources(self, project):
        return self._project_resources.get(project, [])

    def _load_project_recipes(self):
        for project, recipes in self._project_recipes.items():
            for joltdir, src in recipes:
                joltdir = fs.path.join(self.joltdir, joltdir) if joltdir else self.joltdir
                self._load_file(fs.path.join(joltdir, src), joltdir, project)

    def load(self, manifest=None):
        self._load_files()
        self._load_project_recipes()
        return self._tasks, self._tests

    def load_plugins(self):
        searchpath = config.get("jolt", "pluginpath")
        searchpath = searchpath.split(":") if searchpath else []
        searchpath.append(fs.path.join(fs.path.dirname(__file__), "plugins"))

        import jolt.plugins

        for section in config.sections():
            for path in searchpath:
                if "jolt.plugins." + section not in sys.modules:
                    module = fs.path.join(fs.path.dirname(__file__), path, section + ".py")
                    if fs.path.exists(module):
                        imp.load_source("jolt.plugins." + section, module)
                        continue

    def get_sources(self):
        return self._source.items()

    @property
    def joltdir(self):
        return self._path

    def set_joltdir(self, value):
        self._path = value


class RecipeExtension(ManifestExtension):
    def export_manifest(self, manifest, task):
        loader = JoltLoader.get()
        for path, source in loader.get_sources():
            manifest_recipe = manifest.create_recipe()
            manifest_recipe.path = fs.path.basename(path)
            manifest_recipe.source = base64.encodestring(source.encode()).decode()

        projects = set([task.task.joltproject for task in [task] + task.children])
        for project in filter(lambda x: x is not None, projects):
            manifest_project = manifest.create_project()
            manifest_project.name = project

            for name, resource_task in loader._get_project_resources(project):
                resource = manifest_project.create_resource()
                resource.name = name
                resource.text = resource_task

            for joltdir, src in loader._get_project_recipes(project):
                recipe = manifest_project.create_recipe()
                recipe.src = src
                if joltdir:
                    recipe.joltdir = joltdir


    def import_manifest(self, manifest):
        loader = JoltLoader.get()
        loader.set_joltdir(manifest.joltdir)

        for recipe in manifest.recipes:
            with open(recipe.path, "w") as f:
                f.write(base64.decodestring(recipe.source.encode()).decode())

        for project in manifest.projects:
            for recipe in project.recipes:
                loader._add_project_recipe(project.name, recipe.joltdir, recipe.src)

            for resource in project.resources:
                loader._add_project_resource(project.name, resource.name, resource.text)

                # Acquire resource immediately
                task = TaskRegistry.get().get_task(resource.text, manifest=manifest)
                raise_task_error_if(not isinstance(task, WorkspaceResource), task,
                                    "only workspace resources are allowed in manifest")
                task.acquire_ws()

ManifestExtensionRegistry.add(RecipeExtension())
