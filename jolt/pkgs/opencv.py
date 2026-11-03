from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, compiler, protobuf
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.options("options_{system}")
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
    options_windows = ["CMAKE_ASM_COMPILER=OFF"]
    """
    The MLAS kernels of the DNN module are GNU assembly for ELF, which MSVC can't
    build. Without an assembler, OpenCV uses its own SGEMM instead of MLAS;
    otherwise CMake finds the MinGW compiler of the build host.
    """


TaskRegistry.get().add_task_class(OpenCV)
