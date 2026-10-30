from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, compiler, protobuf
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class OpenCV(cmake.CMake):
    name = "opencv"
    version = Parameter("5.0.0", help="OpenCV version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/opencv/opencv.git,rev={version}"]
    srcdir = "{git[opencv]}"
    options = [
        "BUILD_EXAMPLES=OFF",
        "BUILD_TESTS=OFF",
        "BUILD_PERF_TESTS=OFF",
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(OpenCV)
