from jolt import attributes, Alias, BooleanParameter, Download, Parameter
from jolt.pkgs import cmake, compiler, re2c
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.system
@attributes.common_metadata()
class NinjaBin(Download):
    name = "ninja/bin"
    version = Parameter("1.13.2", help="Ninja version.")
    url = ["https://github.com/ninja-build/ninja/releases/download/v{version}/ninja-{ninja_system}.zip"]
    collect = [{"files": "*", "dest": "bin/"}]

    @property
    def ninja_system(self):
        if self.system == "darwin":
            return "mac"
        if self.system == "windows":
            return "win"
        return self.system


@attributes.requires("requires_git")
@attributes.requires("requires_re2c")
@cmake.requires()
@attributes.requires("requires_compiler")
class NinjaSrc(cmake.CMake):
    name = "ninja/src"
    version = Parameter("1.13.2", help="Ninja version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/ninja-build/ninja.git,rev=v{version}"]
    requires_re2c = ["re2c"]
    srcdir = "{git[ninja]}"
    options = ["BUILD_TESTING={tests[ON,OFF]}"]


class Ninja(Alias):
    name = "ninja"
    version = Parameter("1.13.2", help="Ninja version.")
    requires = ["ninja/bin:version={version}"]


TaskRegistry.get().add_task_class(Ninja)
TaskRegistry.get().add_task_class(NinjaBin)
TaskRegistry.get().add_task_class(NinjaSrc)
