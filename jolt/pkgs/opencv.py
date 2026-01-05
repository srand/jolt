from jolt import attributes, Parameter
from jolt.pkgs import cmake, protobuf
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class OpenCV(cmake.CMake):
    name = "opencv"
    version = Parameter("4.12.0", help="OpenCV version.")
    requires_git = ["git:url=https://github.com/opencv/opencv.git,rev={version}"]
    srcdir = "{git[opencv]}"


TaskRegistry.get().add_task_class(OpenCV)
