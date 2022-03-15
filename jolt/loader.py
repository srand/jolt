import glob
import imp
import os
import sys

from jolt import inspect
from jolt.tasks import attributes
from jolt.tasks import Alias, Task, TaskGenerator, TaskRegistry, WorkspaceResource
from jolt.error import raise_error_if, raise_task_error_if
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.manifest import ManifestExtension
from jolt.manifest import ManifestExtensionRegistry


class Recipe(object):
    def __init__(self, path, joltdir=None, project=None, source=None):
        self.path = path
        self.basepath = os.path.basename(path)
        self.joltdir = joltdir
        self.project = project
        self.source = source
        self.tasks = []

    def load(self):
        raise_error_if(self.source is not None, "recipe already loaded: {}", self.path)

        with open(self.path) as f:
            self.source = f.read()

    def save(self):
        raise_error_if(self.source is None, "recipe source unknown: {}", self.path)

        with open(self.path, "w") as f:
            f.write(self.source)


class NativeRecipe(Recipe):
    @staticmethod
    def _is_abstract(cls):
        return cls.__dict__.get("abstract", False) or cls.__name__.startswith("_")

    @staticmethod
    def _is_task(cls):
        return isinstance(cls, type) and \
            issubclass(cls, Task) and \
            not NativeRecipe._is_abstract(cls)

    def load(self):
        super(NativeRecipe, self).load()

        name = utils.canonical(self.path)
        module = imp.load_source("joltfile_{0}".format(name), self.path)
        classes = inspect.getmoduleclasses(module, [Task, TaskGenerator], NativeRecipe._is_abstract)
        generators = []

        for cls in classes[TaskGenerator]:
            cls.joltdir = self.joltdir or os.path.dirname(self.path)
            generators.append(cls())

        for generator in generators:
            generated_tasks = utils.as_list(generator.generate())
            classes[Task] += filter(NativeRecipe._is_task, generated_tasks)

        for task in classes[Task]:
            task.name = task.name or task.__name__.lower()
            task.joltdir = self.joltdir or os.path.dirname(self.path)
            task.joltproject = self.project
            self.tasks.append(task)

        log.verbose("Loaded: {0}", self.path)


class Loader(object):
    def recipes(self):
        pass


class LoaderFactory(object):
    def create(self):
        raise NotImplementedError()


class NativeLoader(Loader):
    def __init__(self, searchpath):
        self._recipes = []
        self._find_files(searchpath)

    def _find_files(self, searchpath):
        files = glob.glob(fs.path.join(searchpath, "*.jolt"))
        for filepath in files:
            recipe = NativeRecipe(filepath)
            self._recipes.append(recipe)

    @property
    def recipes(self):
        return self._recipes


_loaders = []


def register(factory):
    raise_error_if(not issubclass(factory, LoaderFactory),
                   "{} is not a LoaderFactory", factory.__name__)
    _loaders.append(factory)


@register
class NativeLoaderFactory(LoaderFactory):
    def create(self, searchpath):
        return NativeLoader(searchpath)


@utils.Singleton
class JoltLoader(object):
    filename = "*.jolt"

    def __init__(self):
        self._recipes = []
        self._tasks = []
        self._path = None
        self._project_modules = {}
        self._project_recipes = {}
        self._project_resources = {}

    def _add_project_module(self, project, src):
        modules = self._project_modules.get(project, [])
        modules.append(src)
        self._project_modules[project] = modules

    def _get_project_modules(self, project):
        return self._project_modules.get(project, [])

    def _add_project_recipe(self, project, joltdir, src):
        recipes = self._project_recipes.get(project, [])
        recipes.append((joltdir, src))
        self._project_recipes[project] = recipes

    def _get_project_recipes(self, project):
        return self._project_recipes.get(project, [])

    def _add_project_resource(self, project, resource_name, resource_task):
        class ProjectResource(Alias):
            name = project + "/" + resource_name
            requires = [resource_task]

        self._tasks.append(ProjectResource)
        resources = self._project_resources.get(project, [])
        resources.append((resource_name, resource_task))
        self._project_resources[project] = resources

    def _get_project_resources(self, project):
        return self._project_resources.get(project, [])

    def _load_project_recipes(self):
        for project, recipes in self._project_recipes.items():
            resources = [resource for _, resource in self._get_project_resources(project)]
            for joltdir, src in recipes:
                joltdir = fs.path.join(self.joltdir, joltdir) if joltdir else self.joltdir
                recipe = NativeRecipe(fs.path.join(self._path, src), joltdir, project)
                recipe.load()
                for task in recipe.tasks:
                    task._resources = resources
                    attributes.requires("_resources")(task)
                self._tasks += recipe.tasks

    def _find_joltdir(self, searchdir):
        for factory in _loaders:
            loader = factory().create(searchdir)
            if loader.recipes:
                return searchdir

        parentdir = os.path.dirname(searchdir)
        if searchdir == parentdir:
            return None

        return self._find_joltdir(parentdir)

    def _get_searchpaths(self):
        return [self.joltdir]

    def load(self, manifest=None):
        if not self.joltdir:
            self.set_joltdir(self._find_joltdir(os.getcwd()))

        if not self.joltdir:
            return []

        for searchpath in self._get_searchpaths():
            for factory in _loaders:
                loader = factory().create(searchpath)
                for recipe in loader.recipes:
                    recipe.load()
                    self._recipes.append(recipe)
                    self._tasks += recipe.tasks

        self._load_project_recipes()
        return self._tasks

    def load_plugin(self, filepath):
        plugin, ext = os.path.splitext(fs.path.basename(filepath))
        imp.load_source("jolt.plugins." + plugin, filepath)

    def load_plugins(self):
        searchpath = config.get("jolt", "pluginpath")
        searchpath = searchpath.split(":") if searchpath else []
        searchpath.append(fs.path.join(fs.path.dirname(__file__), "plugins"))

        for plugin in config.plugins():
            for path in searchpath:
                if "jolt.plugins." + plugin not in sys.modules:
                    module = fs.path.join(fs.path.dirname(__file__), path, plugin + ".py")
                    if fs.path.exists(module):
                        self.load_plugin(module)
                        continue

    @property
    def recipes(self):
        return self._recipes

    @property
    def tasks(self):
        return self._tasks

    @property
    def joltdir(self):
        return self._path

    def set_joltdir(self, value):
        if not self._path or len(value) < len(self._path):
            self._path = value


class RecipeExtension(ManifestExtension):
    def export_manifest(self, manifest, task):
        loader = JoltLoader.get()

        for recipe in loader.recipes:
            manifest_recipe = manifest.create_recipe()
            manifest_recipe.path = recipe.basepath
            manifest_recipe.source = recipe.source

        projects = set([task.task.joltproject for task in [task] + task.extensions + task.descendants])
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

            for src in loader._get_project_modules(project):
                module = manifest_project.create_module()
                module.src = src

    def import_manifest(self, manifest):
        loader = JoltLoader.get()
        loader.set_joltdir(manifest.joltdir)

        for recipe in manifest.recipes:
            recipe = Recipe(recipe.path, source=recipe.source)
            recipe.save()

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

            for module in project.modules:
                loader._add_project_module(project.name, module.src)
                sys.path.append(fs.path.join(manifest.joltdir, module.src))


ManifestExtensionRegistry.add(RecipeExtension())


def get_workspacedir():
    workspacedir = JoltLoader.get().joltdir
    assert workspacedir is not None, "No workspace present"
    return workspacedir
