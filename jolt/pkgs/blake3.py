from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class Blake3(cmake.CMake):
    name = "blake3"
    version = Parameter("1.8.3", help="blake3 version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/BLAKE3-team/BLAKE3.git,rev={version}"]
    srcdir = "{git[BLAKE3]}/c"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(Blake3)
