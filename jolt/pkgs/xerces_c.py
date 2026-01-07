from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class XercesC(cmake.CMake):
    name = "xerces-c"
    version = Parameter("3.3.0", help="Xerces-C version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_git = ["git:url=https://github.com/apache/xerces-c.git,rev=v{version}"]
    srcdir = "{git[xerces-c]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(XercesC)
