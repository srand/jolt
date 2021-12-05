import json
from os import path

from jolt import Task
from jolt import influence
from jolt.error import raise_task_error_if


@influence.attribute("conanfile")
@influence.attribute("generators")
@influence.attribute("incremental")
@influence.attribute("options")
@influence.attribute("packages")
class Conan(Task):
    """
    Conan package installer task.

    This task base class can be used to fetch, build and publish Conan packages
    as Jolt artifacts. All package metadata is transfered from the Conan package
    manifest to the Jolt artifact so that no manual configuration of include
    paths, library paths, macros, etc is required.

    An existing installation of Conan is required. Please visit https://conan.io/
    for installation instructions and documentation.

    A minimal task to download and publish the Boost C++ libraries can look like this:

    .. code-block:: python

        from jolt.plugins.conan import Conan

        class Boost(Conan):
            packages = ["boost/1.74.0"]

    Boost may then be used from Ninja tasks by declaring a requirement:

    .. code-block:: python

        from jolt.plugins.ninja import CXXExecutable

        class BoostApplication(CXXExecutable):
            requires = ["boost"]
            sources = ["main.cpp"]

    The task supports using an existing conanfile.txt, but it is not required.
    Packages are installed into and collected from Jolt build directories. The
    user's regular Conan cache will not be affected.

    """

    abstract = True

    conanfile = None
    """
    An existing conanfile.txt file to use.

    Instead of generating the conanfile.txt file on-demand, an external
    file may be used. If this attribute is set, the ``generators``, ``options``
    and ``packages`` attributes must not be set.

    See Conan documentation for further details.
    """

    packages = []
    """
    A list of Conan package references to collect and publish.

    The reference format is ``PkgName/<version>@user/channel``. See Conan
    documentation for further details.

    Any {keyword} arguments, or macros, found in the strings are automatically
    expanded to the value of the associated task's parameters and properties.

    Example:

    .. code-block:: python

        sdl_version = Parameter("2.0.12")

        packages = [
            "boost/1.74.0",
            "sdl2/{sdl_version}@bincrafters/stable",
        ]

    """

    options = []
    """
    A list of Conan package options to apply

    The option format is ``PkgName:Option=Value``. See Conan
    documentation for further details.

    Any {keyword} arguments, or macros, found in the strings are automatically
    expanded to the value of the associated task's parameters and properties.

    Example:

    .. code-block:: python

        options = [
            "boost:shared=True",
            "zlib:shared=True",
        ]

    """

    settings = []
    """
    A list of Conan settings to apply

    The settings format is ``Option=Value``. See Conan
    documentation for further details.

    Any {keyword} arguments, or macros, found in the strings are automatically
    expanded to the value of the associated task's parameters and properties.

    Example:

    .. code-block:: python

        settings = [
            "compiler.libcxx=libstdc++11",
        ]

    """

    generators = []
    """
    A list of Conan generators to use.

    See Conan documentation for details about supported generators.
    The json generator is always used.

    Example:

    .. code-block:: python

        generators = ["cmake"]

    """

    remotes = {}
    """
    A dictionary with Conan remotes to use when fetching packages.

    The dictionary key is the name of remote and its value is the URL.

    Example:

    .. code-block:: python

        remotes = {
            "bincrafters": "https://api.bintray.com/conan/bincrafters/public-conan"
        }

    """

    incremental = True
    """
    Keep installed packages in the Conan cache between Jolt invokations.

    If incremental build is disabled, the Jolt Conan cache is removed
    before execution begins.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.conanfile:
            self.influence.append(influence.FileInfluence(self.conanfile))

    def _generators(self):
        return ["json"] + self.generators

    def _options(self):
        return [] + self.options

    def _settings(self):
        return [] + self.settings

    def _packages(self):
        return [] + self.packages

    def _remotes(self):
        return self.remotes

    def run(self, deps, tools):
        raise_task_error_if(
            not tools.which("conan"), self,
            "Conan: Conan is not installed in the PATH")
        raise_task_error_if(
            self.conanfile and (self._generators() or self._packages() or self._options()), self,
            "Conan: 'conanfile' attribute cannot be used with other attributes")

        conanfile = tools.expand_path(self.conanfile) if self.conanfile else None

        with tools.cwd(tools.builddir()):
            if conanfile is None or not path.exists(conanfile):
                conanfile = "conanfile.txt"
                self.info("Creating conanfile.txt")
                self.tools.write_file(conanfile, "[requires]\n")
                for pkg in self._packages():
                    self.tools.append_file(conanfile, pkg + "\n")

            with tools.environ(CONAN_USER_HOME=tools.builddir("conan", incremental=self.incremental)):
                for remote, url in self._remotes().items():
                    self.info("Registering remote '{}'", remote)
                    tools.run("conan remote add -f {} {}", remote, url, output_on_error=True)

                self.info("Installing packages into the Conan cache")
                generators = " ".join(["-g " + gen for gen in self._generators()])
                options = " ".join(["-o " + opt for opt in self._options()])
                settings = " ".join(["-s " + opt for opt in self._settings()])
                tools.run("conan install --build=missing -u -if . {} {} {} {}", generators, options, settings, conanfile)

            self.info("Parsing manifest")
            self._manifest = json.loads(tools.read_file("conanbuildinfo.json"))

            for dep in self._manifest["dependencies"]:
                self.info("Collecting '{}' files from: {}", dep["name"], dep["rootpath"])
                tools.copy(dep["rootpath"], dep["name"])

    def publish(self, artifact, tools):
        self.info("Publishing package files")
        with tools.cwd(tools.builddir()):
            artifact.collect("*")

        self.info("Publishing metadata")
        for dep in self._manifest["dependencies"]:
            for incpath in dep["include_paths"]:
                artifact.cxxinfo.incpaths.append(path.join(dep["name"], path.relpath(incpath, dep["rootpath"])))
            for libpath in dep["lib_paths"]:
                artifact.cxxinfo.libpaths.append(path.join(dep["name"], path.relpath(libpath, dep["rootpath"])))
            for binpath in dep["bin_paths"]:
                artifact.environ.PATH.append(path.join(dep["name"], path.relpath(binpath, dep["rootpath"])))
            artifact.cxxinfo.libraries.append(dep["libs"])
            artifact.cxxinfo.libraries.append(dep["system_libs"])
            artifact.cxxinfo.macros.append(dep["defines"])
            artifact.cxxinfo.cflags.append(dep["cflags"])
            artifact.cxxinfo.cxxflags.append(dep["cxxflags"])
            artifact.cxxinfo.ldflags.append(dep["exelinkflags"])
