from jolt import attributes
from jolt import influence
from jolt import Task
from jolt import utils
from jolt.error import raise_task_error_if

import os


def options(attrib):
    """
    Decorates a CMake task with an alternative ``options`` attribute.

    The new attribute will be concatenated with the regular
    ``options`` attribute.

    Args:
        attrib (str): Name of alternative attribute.
            Keywords are expanded.
    """
    return utils.concat_attributes("options", attrib)


def requires(version=None):
    """ Decorator to add CMake requirements to a task. """

    import jolt.pkgs.cmake

    def decorate(cls):
        cls = attributes.requires("requires_cmake")(cls)
        cls.requires_cmake = ["cmake" + (f":version={version}" if version else "")]
        return cls

    return decorate


def use_ninja():
    """
    Decorator to add Ninja dependencies to CMake task.

    It also selects Ninja as the CMake generator and builder.
    """

    import jolt.pkgs.ninja

    def decorate(cls):
        cls = attributes.requires("requires_ninja")(cls)
        cls.generator = "Ninja"
        cls.requires_ninja = ["ninja"]
        return cls

    return decorate


@attributes.common_metadata()
@options("options")
class CMake(Task):
    """ Builds and publishes a CMake project """
    abstract = True

    cmakelists = "CMakeLists.txt"
    """ Path to CMakeLists.txt or directory containing CMakelists.txt """

    config = "Release"
    """ The default build configuration to use """

    generator = None
    """ The build file generator that CMake should use """

    incremental = True
    """ Keep build directories between Jolt invocations """

    options = []
    """ List of options and their values (``option[:type]=value``) """

    srcdir = None
    """ Source directory. If not specified, the task working directory is used. """

    install = ["install"]
    """ List of install build targets. If empty, the default install target is used. """

    def clean(self, tools):
        cmake = tools.cmake(incremental=self.incremental)
        cmake.clean()

    def run(self, deps, tools):
        self.deps = deps
        raise_task_error_if(not self.cmakelists, self, "cmakelists attribute has not been defined")

        config = tools.expand(str(self.config))
        options = self._options()
        options += ["CMAKE_BUILD_TYPE=" + config]

        with tools.cwd(self.srcdir or self.joltdir):
            cmake = tools.cmake(deps, incremental=self.incremental)
            cmake.configure(tools.expand(self.cmakelists), *["-D" + tools.expand(option) for option in options], generator=self.generator)
            for target in self.install or ["install"]:
                cmake.install(config=config, target=target)

    def publish(self, artifact, tools):
        cmake = tools.cmake(incremental=self.incremental)
        cmake.publish(artifact)


@influence.attribute("headers", type=influence.FileInfluence)
@influence.attribute("sources", type=influence.FileInfluence)
class _CMakeCXX(CMake):
    asflags = []
    binary = None
    cflags = []
    cxxflags = []
    headers = []
    incpaths = []
    ldflags = []
    macros = []
    shared = False
    sources = []

    generator = None
    incremental = True
    template = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.binary = self.binary or self.canonical_name

    def run(self, deps, tools):
        with tools.cwd(tools.builddir(incremental=self.incremental)):
            self.cmakelists = tools.expand_path(self.cmakelists)
            project = utils.render(self.template, deps=deps, task=self, tools=tools, os=os)
            tools.write_file(self.cmakelists, project, expand=False)
        super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.headers:
            for header in self.headers:
                artifact.collect(header)
            artifact.cxxinfo.incpaths.append(".")


class CXXLibrary(_CMakeCXX):
    abstract = True
    template = "cxxlibrary.cmake.template"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.headers:
            for header in self.headers:
                artifact.collect(header)
            artifact.cxxinfo.incpaths.append(".")
        artifact.cxxinfo.libraries.append("{binary}")
        artifact.cxxinfo.libpaths.append("lib")


class CXXExecutable(_CMakeCXX):
    abstract = True
    template = "cxxexecutable.cmake.template"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
