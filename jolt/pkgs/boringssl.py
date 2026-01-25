from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import nasm
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_nasm_{system}")
@attributes.common_metadata()
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["ssl", "crypto"])
class BoringSSL(cmake.CMake):
    name = "boringssl"
    version = Parameter("0.20251124.0", help="boringssl version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/google/boringssl.git,rev={version}"]
    requires_nasm_windows = ["nasm"]
    srcdir = "{git[boringssl]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(BoringSSL)
