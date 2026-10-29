from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import nasm
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_nasm_{system}")
@attributes.common_metadata()
@attributes.system
@cmake.options("options_{system}")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["ssl", "crypto"])
@attributes.requires("requires_compiler")
class BoringSSL(cmake.CMake):
    name = "boringssl"
    version = Parameter("0.20261020.0", help="BoringSSL version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/google/boringssl.git,rev={version}"]
    requires_nasm_windows = ["nasm"]
    srcdir = "{git[boringssl]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]
    options_linux = [
        # GCC 15 finds an overflow in the Keccak code that can't happen, and
        # warnings are errors
        "CMAKE_C_FLAGS=-Wno-error=stringop-overflow",
        "CMAKE_CXX_FLAGS=-Wno-error=stringop-overflow",
    ]
    """ Options passed to CMake on Linux. """


TaskRegistry.get().add_task_class(BoringSSL)
