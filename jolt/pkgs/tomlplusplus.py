from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class TomlPlusPlus(cmake.CMake):
    name = "tomlplusplus"
    version = Parameter("3.4.0", help="TomlPlusPlus version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_git = ["git:url=https://github.com/marzer/tomlplusplus.git,rev=v{version}"]
    srcdir = "{git[tomlplusplus]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(TomlPlusPlus)
