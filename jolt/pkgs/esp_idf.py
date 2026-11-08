import os
import shutil
import sys

from jolt import attributes, Alias, Parameter, Task
from jolt.pkgs import compiler, cpython
from jolt.plugins import fetch, git, python
from jolt.tasks import TaskRegistry


class _EspIdfVersion(object):
    @property
    def _major_minor(self):
        return ".".join(str(self.version).split(".")[:2])


_GIT = "git:url=https://github.com/espressif/esp-idf.git,rev=v{version},shallow=true"
_CONSTRAINTS = "fetch:alias=constraints,url=https://dl.espressif.com/dl/esp-idf/espidf.constraints.v{_major_minor}.txt"


@attributes.requires("requires_git")
class EspIdfSource(Task, _EspIdfVersion):
    """ The ESP-IDF framework: components, build system and idf.py """

    name = "esp-idf/src"
    version = Parameter("6.1", help="ESP-IDF version.")
    requires_git = [_GIT + ",submodules=true"]

    def run(self, deps, tools):
        self.srcdir = tools.builddir("src", incremental=False)
        shutil.copytree(
            tools.expand_path("{git[esp-idf]}"), self.srcdir,
            symlinks=True, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git"))
        # As in release archives. Without git, the build system and idf_tools.py
        # take the version from this file.
        with tools.cwd(self.srcdir):
            tools.write_file("version.txt", "v{version}\n")

    def publish(self, artifact, tools):
        with tools.cwd(self.srcdir):
            artifact.collect("*", symlinks=True)
            artifact.collect(".*", symlinks=True)
        artifact.environ.ESP_IDF_VERSION = "{_major_minor}"
        artifact.environ.IDF_PATH = "."
        artifact.environ.PATH.append("tools")


@attributes.system
@attributes.requires("requires_constraints")
@attributes.requires("requires_git")
class EspIdfTools(Task, _EspIdfVersion):
    """
    The tools that ESP-IDF needs for the chips: compilers, debuggers, OpenOCD
    and ROM ELF files.

    The versions are those that the ESP-IDF release pins, installed by its
    idf_tools.py from the prebuilt releases of Espressif.
    """

    name = "esp-idf/tools"
    version = Parameter("6.1", help="ESP-IDF version.")
    targets = Parameter("all", help="Chips to install tools for, separated by commas (esp32,esp32c3).")
    requires_constraints = [_CONSTRAINTS]
    requires_git = [_GIT]

    def _idf_tools(self, tools, *args, output=True):
        # idf_tools.py only needs the standard library
        return tools.run(
            [sys.executable, tools.expand_path("{git[esp-idf]}/tools/idf_tools.py"), "--non-interactive", *args],
            shell=False, output=output)

    def run(self, deps, tools):
        self.installdir = tools.builddir("tools", incremental=False)
        # idf_tools.py refuses to run in MSYS2 shells, such as Git Bash, but it
        # only needs the variable that identifies them to be unset
        with tools.environ(IDF_TOOLS_PATH=self.installdir, IDF_PATH=tools.expand_path("{git[esp-idf]}"), MSYSTEM=None):
            self._idf_tools(tools, "install", "--targets={}".format(tools.expand("{targets}")), "required")
            exports = self._idf_tools(tools, "export", "--format", "key-value", output=False)

        # The directories of the tools' executables, relative to the artifact
        self.bindirs = []
        installdir = os.path.normcase(os.path.normpath(self.installdir))
        for line in exports.splitlines():
            if not line.startswith("PATH="):
                continue
            for path in line[len("PATH="):].split(os.pathsep):
                # Separators and case of drive letters differ on Windows
                path = os.path.normcase(os.path.normpath(path))
                if path.startswith(installdir + os.sep):
                    self.bindirs.append(os.path.relpath(path, installdir))

        # idf.py checks the Python environment against the constraints
        constraints = tools.expand_path("{fetch[constraints]}")
        with tools.cwd(self.installdir):
            # The downloaded archives
            tools.rmtree("dist", ignore_errors=True)
            tools.copy(constraints, "espidf.constraints.v{_major_minor}.txt")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.environ.IDF_TOOLS_PATH = "."
        for bindir in self.bindirs:
            artifact.environ.PATH.append(bindir)


@python.requires()
@attributes.requires("requires_compiler")
@attributes.requires("requires_constraints")
@attributes.requires("requires_git")
class EspIdfPython(python.PythonEnv, _EspIdfVersion):
    """ Python environment with the packages that ESP-IDF and idf.py need """

    name = "esp-idf/python"
    version = Parameter("6.1", help="ESP-IDF version.")
    # tree-sitter is built from source for new Python releases
    requires_compiler = ["virtual/compiler/c"]
    requires_constraints = [_CONSTRAINTS]
    requires_git = [_GIT]

    def publish(self, artifact, tools):
        # The packages of the core feature, pinned by the constraints of the release
        # pip parses the requirements file like a shell, so backslashes in
        # Windows paths are escape characters
        self.requirements = [
            "-r " + tools.expand_path("{git[esp-idf]}/tools/requirements/requirements.core.txt").replace("\\", "/"),
            "-c " + tools.expand_path("{fetch[constraints]}").replace("\\", "/"),
        ]
        super().publish(artifact, tools)
        if self.system == "windows":
            # idf_tools.py looks for the interpreter of virtual environments,
            # Scripts/python.exe. Python finds its prefix by searching up for
            # lib/os.py, and the DLLs are loaded from the directory of the
            # executable.
            with tools.cwd(artifact.path):
                tools.copy("bin/python3.exe", "Scripts/python.exe")
                for dll in tools.glob("bin/*.dll"):
                    tools.copy(dll, "Scripts/")
        # The artifact path itself: idf.py checks that the interpreter's path
        # starts with it, which "." in the path breaks
        artifact.environ.IDF_PYTHON_ENV_PATH = ""


class EspIdf(Alias):
    """
    Espressif IoT Development Framework, with the tools and the Python
    environment that idf.py needs. Consumers run idf.py.
    """

    name = "esp-idf"
    version = Parameter("6.1", help="ESP-IDF version.")
    targets = Parameter("all", help="Chips to install tools for, separated by commas (esp32,esp32c3).")
    requires = [
        "esp-idf/src:version={version}",
        "esp-idf/python:version={version}",
        "esp-idf/tools:version={version},targets={targets}",
    ]


TaskRegistry.get().add_task_class(EspIdf)
TaskRegistry.get().add_task_class(EspIdfPython)
TaskRegistry.get().add_task_class(EspIdfSource)
TaskRegistry.get().add_task_class(EspIdfTools)
