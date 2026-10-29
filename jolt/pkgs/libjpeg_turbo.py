from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, nasm
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_nasm")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class LibjpegTurbo(cmake.CMake):
    name = "libjpeg-turbo"
    version = Parameter("3.2.1", help="libjpeg-turbo version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/libjpeg-turbo/libjpeg-turbo.git,rev={version}"]
    requires_nasm = ["nasm"]
    srcdir = "{git[libjpeg-turbo]}"
    options = [
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "ENABLE_SHARED={shared[ON,OFF]}",
        "ENABLE_STATIC={shared[OFF,ON]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("jpeg{shared[,-static]}")
            artifact.cxxinfo.libraries.append("turbojpeg{shared[,-static]}")
        else:
            artifact.cxxinfo.libraries.append("jpeg")
            artifact.cxxinfo.libraries.append("turbojpeg")


TaskRegistry.get().add_task_class(LibjpegTurbo)
