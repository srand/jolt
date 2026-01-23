from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry
import os


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Abseil(cmake.CMake):
    """ Abseil C++ Common Libraries """

    name = "abseil"
    version = Parameter("20250814.1")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_git = ["git:url=https://github.com/abseil/abseil-cpp.git,rev={version}"]
    srcdir = "{git[abseil-cpp]}"
    options = [
        "ABSL_MSVC_STATIC_RUNTIME=OFF",
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_CXX_STANDARD=17",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.msvcrt = "Dynamic"
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")

        with tools.cwd(artifact.path, "lib"):
            for libfile in tools.glob("*.lib"):
                libname, _ = os.path.splitext(libfile)
                artifact.cxxinfo.libraries.append(libname)
            for libfile in tools.glob("lib*.a"):
                libname, _ = os.path.splitext(libfile)
                artifact.cxxinfo.libraries.append(libname[3:])


TaskRegistry.get().add_task_class(Abseil)
