from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class MagicEnum(cmake.CMake):
    """ Static reflection for enums in C++ """

    name = "magic_enum"
    version = Parameter("0.9.8", help="magic_enum version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/Neargye/magic_enum.git,rev=v{version}"]
    srcdir = "{git[magic_enum]}"
    options = [
        "MAGIC_ENUM_OPT_BUILD_EXAMPLES=OFF",
        "MAGIC_ENUM_OPT_BUILD_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(MagicEnum)
