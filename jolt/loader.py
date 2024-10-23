from collections import OrderedDict
from contextlib import contextmanager
import fasteners
import json
import glob
from importlib.machinery import SourceFileLoader
import os
import platform
import subprocess
import sys
from types import ModuleType

from jolt import inspection
from jolt.tasks import attributes
from jolt.tasks import Alias, Task, TaskGenerator, TaskRegistry, WorkspaceResource
from jolt.error import raise_error_if, raise_task_error_if
from jolt import common_pb2 as common_pb
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.manifest import ManifestExtension
from jolt.manifest import ManifestExtensionRegistry
from jolt.tools import Tools


class Recipe(object):
    def __init__(self, path, joltdir=None, project=None, source=None):
        self.path = path
        self.basepath = os.path.basename(path)
        self.joltdir = joltdir
        self.project = project
        self.source = source
        self.tasks = []

    def load(self, joltdir=None):
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

    def load(self, joltdir=None):
        super(NativeRecipe, self).load()

        name = utils.canonical(self.path)
        loader = SourceFileLoader("joltfile_{0}".format(name), self.path)
        module = ModuleType(loader.name)
        module.__file__ = self.path
        loader.exec_module(module)
        sys.modules[loader.name] = module

        classes = inspection.getmoduleclasses(module, [Task, TaskGenerator], NativeRecipe._is_abstract)
        generators = []

        for cls in classes[TaskGenerator]:
            cls.joltdir = os.path.normpath(joltdir or self.joltdir or os.path.dirname(self.path))
            generators.append(cls())

        for generator in generators:
            generated_tasks = utils.as_list(generator.generate())
            classes[Task] += filter(NativeRecipe._is_task, generated_tasks)

        for task in classes[Task]:
            task.name = task.name or task.__name__.lower()
            task.joltdir = os.path.normpath(joltdir or self.joltdir or os.path.dirname(self.path))
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
        self._files = self._find_files(searchpath)
        self._recipes = self._load_files(self._files) if self._files else []

    def _find_files(self, searchpath):
        # If the searchpath is a file, load it directly
        if fs.path.isdir(searchpath):
            return glob.glob(fs.path.join(searchpath, "*.jolt"))

        _, ext = fs.path.splitext(searchpath)
        raise_error_if(not fs.path.exists(searchpath), "File does not exist: {}", searchpath)
        raise_error_if(ext not in [".jolt", ".py"], "Invalid file extension: {}", ext)

        return [searchpath]

    def _load_files(self, files):
        recipes = []
        for filepath in files:
            recipe = NativeRecipe(filepath)
            recipes.append(recipe)
        return recipes

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
        self._lock = None
        self._recipes = []
        self._tasks = []
        self._path = None
        self._project_modules = OrderedDict()
        self._project_recipes = OrderedDict()
        self._project_resources = OrderedDict()
        self._build_path = None
        self._workspace_name = None

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

    def _get_first_recipe_path(self):
        for recipe in self.recipes:
            return recipe.path
        for project, recipes in self._project_recipes.items():
            for joltdir, src in recipes:
                return fs.path.join(self._path, src)
        return None

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

    def _find_workspace_path(self, searchdir):
        for factory in _loaders:
            loader = factory().create(searchdir)
            if loader.recipes:
                return searchdir

        parentdir = os.path.dirname(searchdir)
        if searchdir == parentdir:
            return os.getcwd()

        return self._find_workspace_path(parentdir)

    def _get_searchpaths(self):
        return [self.workspace_path]

    def load(self, manifest=None):
        if not self.workspace_path:
            self.set_workspace_path(self._find_workspace_path(os.getcwd()))

        if not self.workspace_path:
            return []

        for searchpath in self._get_searchpaths():
            for factory in _loaders:
                loader = factory().create(searchpath)
                for recipe in loader.recipes:
                    recipe.load()
                    self._recipes.append(recipe)
                    self._tasks += recipe.tasks

        self._load_project_recipes()

        # Create workspace lock on the first loaded recipe
        if not self._lock:
            path = self._get_first_recipe_path()
            if path:
                self._lock = fasteners.InterProcessLock(path)

        return self._tasks

    def load_file(self, path, joltdir=None):
        for factory in _loaders:
            loader = factory().create(path)
            for recipe in loader.recipes:
                joltdir = fs.path.join(self.joltdir, joltdir) if joltdir else self.joltdir
                recipe.load(joltdir=joltdir)
                self._recipes.append(recipe)
                self._tasks += recipe.tasks

    def load_plugin(self, filepath):
        plugin, ext = os.path.splitext(fs.path.basename(filepath))
        loader = SourceFileLoader("jolt.plugins." + plugin, filepath)
        module = ModuleType(loader.name)
        module.__file__ = filepath
        loader.exec_module(module)
        sys.modules[loader.name] = module

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
                    module = fs.path.join(fs.path.dirname(__file__), path, plugin, "__init__.py")
                    if fs.path.exists(module):
                        self.load_plugin(module)
                        continue

    @property
    def projects(self):
        return self._recipes

    @property
    def recipes(self):
        return self._recipes

    @property
    def tasks(self):
        return self._tasks

    @property
    def joltdir(self):
        return self._path

    @property
    def workspace_name(self):
        return self._workspace_name or os.path.basename(self.workspace_path)

    def set_workspace_name(self, name):
        self._workspace_name = name

    @property
    def workspace_path(self):
        return self._path

    @contextmanager
    @utils.locked
    def workspace_lock(self):
        if not self._lock:
            yield
        with self._lock:
            yield

    def set_workspace_path(self, path):
        if not self._path or len(path) < len(self._path):
            self._path = os.path.normpath(path) if path is not None else None

    @property
    def build_path(self):
        return self._build_path or os.path.join(self.workspace_path, "build")

    @property
    def build_path_rel(self):
        return os.path.relpath(self.build_path, self.workspace_path)

    def set_build_path(self, path):
        self._build_path = os.path.normpath(os.path.join(self.workspace_path, path))
        log.debug("Jolt build path: {}", self._build_path)


class RecipeExtension(ManifestExtension):
    def export_manifest(self, manifest, tasks):
        loader = JoltLoader.get()

        for recipe in loader.recipes:
            manifest_recipe = manifest.create_recipe()
            manifest_recipe.path = recipe.basepath
            manifest_recipe.source = recipe.source

        projects = set([task.task.joltproject for task in tasks])
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

            for path in loader._get_project_modules(project):
                module = manifest_project.create_module()
                module.path = path

    def import_manifest(self, manifest):
        loader = JoltLoader.get()
        loader.set_workspace_path(manifest.get_workspace_path() or os.getcwd())
        loader.set_workspace_name(manifest.get_workspace_name())
        if manifest.build:
            loader.set_build_path(manifest.build)

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
                sys.path.append(fs.path.join(manifest.get_workspace_path(), module.src))

    def import_protobuf(self, buildenv):
        loader = JoltLoader.get()
        loader.set_workspace_path(os.getcwd())
        loader.set_workspace_name(buildenv.workspace.name)
        if buildenv.workspace.builddir:
            loader.set_build_path(buildenv.workspace.builddir)

        # Write .jolt files into workspace
        for file in buildenv.workspace.files:
            if file.content:
                with open(file.path, "w") as f:
                    f.write(file.content)

        for project in buildenv.workspace.projects:
            for recipe in project.recipes:
                loader._add_project_recipe(project.name, recipe.workdir, recipe.path)

            for resource in project.resources:
                loader._add_project_resource(project.name, resource.alias, resource.name)

                # Acquire resource immediately
                task = TaskRegistry.get().get_task(resource.name, buildenv=buildenv)
                raise_task_error_if(
                    not isinstance(task, WorkspaceResource), task,
                    "only workspace resources are allowed in manifest")
                task.acquire_ws()

            for path in project.paths:
                loader._add_project_module(project.name, path.path)
                sys.path.append(fs.path.join(loader.workspace_path, path.path))


ManifestExtensionRegistry.add(RecipeExtension())


def get_workspacedir():
    workspacedir = JoltLoader.get().workspace_path
    assert workspacedir is not None, "No workspace present"
    return workspacedir


@contextmanager
def workspace_lock():
    with JoltLoader.get().workspace_lock():
        yield


def workspace_locked(func):
    def wrapper(*args, **kwargs):
        with workspace_lock():
            return func(*args, **kwargs)
    return wrapper


@workspace_locked
def export_workspace(tasks=None):
    loader = JoltLoader.get()
    tools = Tools()
    tree = None

    fstree_enabled = config.getboolean("jolt", "fstree", True)
    if fstree_enabled:
        fstree = tools.which("fstree")
        if not fstree:
            host = platform.system().lower()
            arch = platform.machine().lower()
            fstree = os.path.join(os.path.dirname(__file__), "bin", f"fstree-{host}-{arch}")
        if not os.path.exists(fstree):
            fstree_enabled = False
            log.warning("fstree executable not found, will not push workspace to remote cache")

    cache_grpc_uri = config.geturi("cache", "grpc_uri")
    if fstree_enabled:
        if not cache_grpc_uri:
            log.warning("No cache gRPC URI configured, will not push workspace to remote cache")
        else:
            raise_error_if(cache_grpc_uri.scheme not in ["tcp"], "Invalid scheme in cache gRPC URI config: {}", cache_grpc_uri.scheme)
            raise_error_if(not cache_grpc_uri.netloc, "Invalid network address in cache gRPC URI config: {}", cache_grpc_uri.netloc)

    # Push workspace to remote cache if possible
    if fstree_enabled and fstree and cache_grpc_uri:
        with tools.cwd(loader.workspace_path):
            cwd = tools.getcwd()
            cachedir = config.get_cachedir()
            indexhash = utils.sha1(cwd)
            indexfile = tools.expand_path(
                "{cachedir}/indexes/{}/{}",
                indexhash[:2], indexhash[2:],
                cwd=fs.posixpath.abspath(cwd),
                cachedir=cachedir)

            if not os.path.exists(indexfile):
                process = None
                try:
                    with log.progress("Indexing workspace for the first time", count=None, unit="objects", estimates=False) as progress:
                        process = subprocess.Popen(
                            [fstree, "write-tree", "--json", "--cache", cachedir, "--ignore", ".joltignore", "--index", indexfile, "--remote", cache_grpc_uri.geturl(), "--threads", str(tools.thread_count())],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            cwd=tools.getcwd())

                        for line in iter(process.stderr.readline, b''):
                            try:
                                event = json.loads(line.decode())
                            except json.JSONDecodeError as exc:
                                log.error("Failed to decode fstree event: {}", line.decode())
                                raise exc

                            if event.get("type") in ["cache::add"]:
                                progress.update(1)

                except Exception as exc:
                    if process:
                        process.terminate()
                    raise exc
                finally:
                    if process:
                        process.wait()
                        process.stderr.close()
                        raise_error_if(process.returncode != 0, "Failed to index workspace")

            process = None
            try:
                with log.progress("Pushing workspace to remote cache", count=None, unit="objects", estimates=False) as progress:
                    process = subprocess.Popen(
                        [fstree, "write-tree-push", "--json", "--cache", cachedir, "--ignore", ".joltignore", "--index", indexfile, "--remote", cache_grpc_uri.geturl(), "--threads", str(tools.thread_count())],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        cwd=tools.getcwd())

                    for line in iter(process.stderr.readline, b''):
                        try:
                            event = json.loads(line.decode())
                        except json.JSONDecodeError as exc:
                            log.error("Failed to decode fstree event: {}", line.decode())
                            raise exc

                        if event.get("type") in ["cache::push"]:
                            tree = event.get("path")
                            log.info("Workspace tree: {} ({} objects)", tree, event.get("value"))

                        if event.get("type") in ["cache::remote_missing_object", "cache::remote_missing_tree"]:
                            progress.refresh()

                        if event.get("type") in ["cache::push_object", "cache::push_tree"]:
                            progress.update(1)

            except Exception as exc:
                if process:
                    process.terminate()
                raise exc

            finally:
                if process:
                    process.wait()
                    process.stderr.close()
                    raise_error_if(process.returncode != 0, "Failed to push workspace to remote cache")

    workspace = common_pb.Workspace(
        builddir=loader.build_path_rel,
        cachedir=config.get_cachedir(),
        rootdir=loader.workspace_path,
        name=loader.workspace_name,
        tree=tree,
    )

    for recipe in loader.recipes:
        workspace.files.append(
            common_pb.File(
                path=recipe.basepath,
                content=recipe.source,
            )
        )

    if tasks is None:
        projects = loader._project_recipes.keys()
    else:
        projects = set([task.task.joltproject for task in tasks])

    for project in filter(lambda x: x is not None, projects):
        pb_project = common_pb.Project()
        pb_project.name = project

        for name, resource_task in loader._get_project_resources(project):
            resource = common_pb.Project.Resource()
            resource.alias = name
            resource.name = resource_task
            pb_project.resources.append(resource)

        for joltdir, src in loader._get_project_recipes(project):
            recipe = common_pb.Project.Recipe()
            recipe.path = src
            if joltdir:
                recipe.workdir = joltdir
            pb_project.recipes.append(recipe)

        for path in loader._get_project_modules(project):
            syspath = common_pb.Project.SystemPath(path=path)
            pb_project.paths.append(syspath)

        workspace.projects.append(pb_project)

    return workspace
