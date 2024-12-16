import json
from os import path

from jolt import Task
from jolt import influence
from jolt import utils
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


@influence.attribute("conanfile")
@influence.attribute("generators")
@influence.attribute("incremental")
@influence.attribute("options")
@influence.attribute("packages")
class Conan2(Task):
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
            self.conanfile and (self._packages() or self._options()), self,
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
                options = " ".join(["-o " + opt for opt in self._options()])
                settings = " ".join(["-s " + opt for opt in self._settings()])
                output = tools.run("conan install --build=missing --output-folder . -u --format=json {} {} {}", options, settings, conanfile, output_stdout=False)

            self.info("Parsing manifest")
            self._manifest = json.loads(output)

            for dep in self._manifest["graph"]["nodes"].values():
                if dep["package_folder"]:
                    self.info("Collecting '{}' files from: {}", dep["name"], dep["package_folder"])
                    tools.copy(dep["package_folder"], dep["name"])

    def publish(self, artifact, tools):
        self.info("Publishing package files")
        with tools.cwd(tools.builddir()):
            artifact.collect("*")

        self.info("Publishing metadata")
        for dep in self._manifest["graph"]["nodes"].values():
            if not dep["package_folder"]:
                continue

            for node in dep["cpp_info"]:
                for incpath in dep["cpp_info"][node]["includedirs"]:
                    artifact.cxxinfo.incpaths.append(path.join(dep["name"], path.relpath(incpath, dep["package_folder"])))
                for libpath in dep["cpp_info"][node]["libdirs"]:
                    artifact.cxxinfo.libpaths.append(path.join(dep["name"], path.relpath(libpath, dep["package_folder"])))
                for binpath in dep["cpp_info"][node]["bindirs"]:
                    artifact.environ.PATH.append(path.join(dep["name"], path.relpath(binpath, dep["package_folder"])))
                if dep["cpp_info"][node]["libs"]:
                    artifact.cxxinfo.libraries.extend(dep["cpp_info"][node]["libs"])
                if dep["cpp_info"][node]["system_libs"]:
                    artifact.cxxinfo.libraries.extend(dep["cpp_info"][node]["system_libs"])
                if dep["cpp_info"][node]["defines"]:
                    artifact.cxxinfo.macros.extend(dep["cpp_info"][node]["defines"])
                if dep["cpp_info"][node]["cflags"]:
                    artifact.cxxinfo.cflags.extend(dep["cpp_info"][node]["cflags"])
                if dep["cpp_info"][node]["cxxflags"]:
                    artifact.cxxinfo.cxxflags.extend(dep["cpp_info"][node]["cxxflags"])
                if dep["cpp_info"][node]["exelinkflags"]:
                    artifact.cxxinfo.ldflags.extend(dep["cpp_info"][node]["exelinkflags"])

        # Make list of unique values
        artifact.cxxinfo.incpaths = utils.unique_list(artifact.cxxinfo.incpaths)
        artifact.cxxinfo.libpaths = utils.unique_list(artifact.cxxinfo.libpaths)
        artifact.cxxinfo.libraries = utils.unique_list(artifact.cxxinfo.libraries)
        artifact.cxxinfo.macros = utils.unique_list(artifact.cxxinfo.macros)
        artifact.cxxinfo.cflags = utils.unique_list(artifact.cxxinfo.cflags)
        artifact.cxxinfo.cxxflags = utils.unique_list(artifact.cxxinfo.cxxflags)
        artifact.cxxinfo.ldflags = utils.unique_list(artifact.cxxinfo.ldflags)
        artifact.environ.PATH = path.pathsep.join(utils.unique_list(str(artifact.environ.PATH).split(path.pathsep)))
