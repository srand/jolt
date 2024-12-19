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
from jolt.tasks import Task, TaskGenerator
from jolt.error import raise_error_if
from jolt import common_pb2 as common_pb
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.tools import Tools


class Recipe(object):
    """
    Abstract representation a single recipe file.

    Implementations of this class are responsible for reading the recipe source
    from the filesystem. The recipe source is then parsed and the tasks are
    extracted and made available for execution.

    The format of the recipe source is implementation defined.
    """

    tasks = []
    """
    List of task classes defined in the recipe.

    Available after the recipe has been loaded.
    """

    def __init__(self, path, joltdir=None, project=None, source=None):
        self.path = path
        self.basepath = os.path.basename(path)
        self.joltdir = joltdir
        self.project = project
        self.source = source
        self.tasks = []

    def load(self):
        """ Load the recipe source from the file system. """
        raise_error_if(self.source is not None, "recipe already loaded: {}", self.path)

        with open(self.path) as f:
            self.source = f.read()

    def save(self):
        """ Save the recipe source to the file system. """
        raise_error_if(self.source is None, "recipe source unknown: {}", self.path)

        with open(self.path, "w") as f:
            f.write(self.source)


class NativeRecipe(Recipe):
    """ Represents a Python recipe file (.jolt, .py). """

    @staticmethod
    def _is_abstract(cls):
        return cls.__dict__.get("abstract", False) or cls.__name__.startswith("_")

    @staticmethod
    def _is_task(cls):
        return isinstance(cls, type) and \
            issubclass(cls, Task) and \
            not NativeRecipe._is_abstract(cls)

    def load(self, joltdir=None):
        """
        Load the recipe source from the file system.

        Python classes defined in the recipe source are extracted and made available
        as tasks for execution. Task classes must be subclasses of Task or TaskGenerator.

        """
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
    """
    Base class for recipe loaders.

    A Loader is responsible for finding recipes in the file system providing a list
    of Recipe:s from which tasks can be loaded.
    """

    def recipes(self) -> list:
        """ Return a list of Recipe:s from which tasks can be loaded. """
        pass


class LoaderFactory(object):
    """
    A factory for creating Loader instances.

    Factories are registered with the JoltLoader where it is used to create Loader instances.
    """
    def create(self):
        raise NotImplementedError()


class NativeLoader(Loader):
    """ A loader for Python recipe files (.jolt, .py). """

    def __init__(self, searchpath):
        """
        Create a new NativeLoader instance.

        Args:
            searchpath (str): The path to search for recipe files. If the path is a file,
                only that file will be loaded. If the path is a directory, all files with
                the .jolt or .py extension will be loaded.

        """

        self._files = self._find_files(searchpath)
        self._recipes = self._load_files(self._files) if self._files else []

    def _find_files(self, searchpath):
        # If the searchpath is a file, load it directly
        if fs.path.isdir(searchpath):
            return glob.glob(fs.path.join(searchpath, "*.jolt"))

        _, ext = fs.path.splitext(searchpath)
        raise_error_if(not fs.path.exists(searchpath), "File does not exist: {}", searchpath)
        raise_error_if(ext not in [".build", ".jolt", ".py"], "Invalid file extension: {}", ext)

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
    """ Register a LoaderFactory with the JoltLoader. """
    raise_error_if(not issubclass(factory, LoaderFactory),
                   "{} is not a LoaderFactory", factory.__name__)
    _loaders.append(factory)


@register
class NativeLoaderFactory(LoaderFactory):
    """ A factory for creating NativeLoader instances. """
    def create(self, searchpath):
        return NativeLoader(searchpath)


@utils.Singleton
class JoltLoader(object):
    """
    The JoltLoader is responsible for loading recipes from the file system.

    The JoltLoader is a singleton and is used to load recipes from the file system.
    The recipes are loaded from the workspace directory and any project directories
    defined in the workspace. The recipes are then made available for execution.

    """

    filename = "*.jolt"

    def __init__(self):
        self._lock = None
        self._recipes = []
        self._tasks = []
        self._path = None
        self._build_path = None
        self._workspace_name = None

    def _get_first_recipe_path(self):
        for recipe in self.recipes:
            return recipe.path
        return None

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

    def load(self, registry=None):
        """
        Load all recipes from the workspace directory.

        Optionally populate the task registry with the tasks found in the recipes.

        Returns:
            List of Task classes found in the recipes.
        """

        if not self.workspace_path:
            self.set_workspace_path(self._find_workspace_path(os.getcwd()))

        if not self.workspace_path:
            return []

        for searchpath in self._get_searchpaths():
            for factory in _loaders:
                loader = factory().create(searchpath)
                for recipe in loader.recipes:
                    recipe.workspace_path = os.path.relpath(recipe.path, self.workspace_path)
                    recipe.load()
                    self._recipes.append(recipe)
                    self._tasks += recipe.tasks

        # Create workspace lock on the first loaded recipe
        if not self._lock:
            path = self._get_first_recipe_path()
            if path:
                self._lock = fasteners.InterProcessLock(path)

        # Add tasks to the registry if provided
        if registry is not None:
            for task in self._tasks:
                registry.add_task_class(task)

        return self._tasks

    def load_file(self, path, joltdir=None):
        """ Load a single recipe file. """

        for factory in _loaders:
            loader = factory().create(path)
            for recipe in loader.recipes:
                joltdir = fs.path.join(self.joltdir, joltdir) if joltdir else self.joltdir
                recipe.load(joltdir=joltdir)
                self._recipes.append(recipe)
                self._tasks += recipe.tasks

    def load_plugin(self, filepath):
        """ Load a single plugin file. """

        plugin, ext = os.path.splitext(fs.path.basename(filepath))
        loader = SourceFileLoader("jolt.plugins." + plugin, filepath)
        module = ModuleType(loader.name)
        module.__file__ = filepath
        loader.exec_module(module)
        sys.modules[loader.name] = module

    def load_plugins(self):
        """
        Load all configured plugins.

        Plugins are loaded from the plugin path configured in the Jolt configuration file
        or from the default plugin path in the Jolt package.

        If a plugin is already loaded, it will not be loaded again. If a plugin is not found
        in the plugin path, it will not be loaded.
        """
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
        """ Returns a list of all loaded tasks. """
        return self._tasks

    @property
    def joltdir(self):
        """ Returns the path to the workspace. """
        return self._path

    @property
    def workspace_name(self):
        """ Returns the name of the workspace. """
        return self._workspace_name or os.path.basename(self.workspace_path)

    def set_workspace_name(self, name):
        self._workspace_name = name

    @property
    def workspace_path(self):
        """ Returns the path to the workspace. """
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
        """ Returns the path to the build directory. """
        return self._build_path or os.path.join(self.workspace_path, "build")

    @property
    def build_path_rel(self):
        """" Returns the path to the build directory relative to the workspace. """
        return os.path.relpath(self.build_path, self.workspace_path)

    def set_build_path(self, path):
        self._build_path = os.path.normpath(os.path.join(self.workspace_path, path))
        log.debug("Jolt build path: {}", self._build_path)


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


def import_workspace(buildenv: common_pb.BuildEnvironment):
    """
    Import workspace from a BuildEnvironment protobuf message.

    This function will create files, recipes, resources and modules in the workspace
    based on the information in the BuildEnvironment message.

    The workspace tree is not pulled and checked out here. This is done by the
    worker before it starts the executor.

    """
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


@workspace_locked
def export_workspace(tasks=None) -> common_pb.Workspace:
    """
    Export workspace to a Workspace protobuf message.

    This function will create a Workspace protobuf message containing all the
    recipes, resources and modules in the workspace. If tasks is provided, only
    the projects associated with the tasks will be exported. Otherwise, all
    projects will be exported.

    If the workspace is configured to use a remote cache, the workspace will be
    pushed to the remote cache using the fstree tool. The tree hash of the
    workspace will be included in the returned Workspace message.

    """
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
            fstree_enabled = False
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

    if not fstree_enabled:
        for recipe in loader.recipes:
            workspace.files.append(
                common_pb.File(
                    path=recipe.workspace_path,
                    content=recipe.source,
                )
            )

    return workspace
