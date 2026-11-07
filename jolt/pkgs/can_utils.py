from jolt import attributes, Parameter
from jolt.pkgs import compiler
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class CanUtils(cmake.CMake):
    """ SocketCAN command line utilities: candump, cansend, cangen and others """

    name = "can-utils"
    version = Parameter("2025.01", help="can-utils version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/linux-can/can-utils.git,rev=v{version}"]
    srcdir = "{git[can-utils]}"
    options = ["ENABLE_WERROR=OFF"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("bin")


TaskRegistry.get().add_task_class(CanUtils)
