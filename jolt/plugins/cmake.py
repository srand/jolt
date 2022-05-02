from jolt import influence
from jolt import Task
from jolt import utils
from jolt.error import raise_task_error_if

import os


class CMake(Task):
    """ Builds and publishes a CMake project """

    abstract = True

    cmakelists = "CMakeLists.txt"
    """ Path to CMakeLists.txt or directory containing CMakelists.txt """

    generator = None

    incremental = True

    options = []
    """ List of options and their values (``option[:type]=value``) """

    def run(self, deps, tools):
        raise_task_error_if(not self.cmakelists, self, "cmakelists attribute has not been defined")

        cmake = tools.cmake(incremental=self.incremental)
        cmake.configure(tools.expand(self.cmakelists), *["-D" + tools.expand(option) for option in self.options], generator=self.generator)
        cmake.build()
        cmake.install()

    def publish(self, artifact, tools):
        cmake = tools.cmake()
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
