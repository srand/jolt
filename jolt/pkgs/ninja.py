from jolt import attributes, Alias, BooleanParameter, Download, Parameter
from jolt.pkgs import cmake, re2c
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.arch
@attributes.system
@attributes.common_metadata()
class NinjaBin(Download):
    name = "ninja/bin"
    version = Parameter("1.13.2", help="Ninja version.")
    url = ["https://github.com/ninja-build/ninja/releases/download/v{version}/ninja-{system}.zip"]
    collect = [{"files": "*", "dest": "bin/"}]


@attributes.requires("requires_git")
@attributes.requires("requires_re2c")
@cmake.requires()
class NinjaSrc(cmake.CMake):
    name = "ninja/src"
    version = Parameter("1.13.2", help="Ninja version.")
    tests = BooleanParameter(False, help="Build tests.")
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
