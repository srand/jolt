from jolt import attributes, Parameter
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class Blake3(cmake.CMake):
    name = "blake3"
    version = Parameter("1.8.3", help="blake3 version.")
    requires_git = ["git:url=https://github.com/BLAKE3-team/BLAKE3.git,rev={version}"]
    srcdir = "{git[BLAKE3]}/c"


TaskRegistry.get().add_task_class(Blake3)
