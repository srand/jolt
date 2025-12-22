from jolt import attributes, Parameter
from jolt.pkgs import boost, cmake, double_conversion, fastfloat, glog
from jolt.pkgs import libevent, libunwind
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_boost")
@attributes.requires("requires_cmake")
@attributes.requires("requires_double_conversion")
@attributes.requires("requires_fastfloat")
@attributes.requires("requires_git")
@attributes.requires("requires_glog")
@attributes.requires("requires_libevent")
@attributes.requires("requires_libunwind")
class Folly(cmake.CMake):
    name = "folly"
    version = Parameter("2025.12.22.00", help="folly version.")
    requires_boost = ["boost"]
    requires_cmake = ["cmake"]
    requires_double_conversion = ["double-conversion"]
    requires_fastfloat = ["fastfloat"]
    requires_git = ["git:url=https://github.com/facebook/folly.git,rev=v{version}"]
    requires_glog = ["glog"]
    requires_libevent = ["libevent"]
    requires_libunwind = ["libunwind"]
    srcdir = "{git[folly]}"
    options = [
        # "DOUBLE_CONVERSION_INCLUDE_DIR={deps[double-conversion].path}/include",
        # "DOUBLE_CONVERSION_LIBRARY={deps[double-conversion].path}/lib/libdouble-conversion.so",
        # "FASTFLOAT_INCLUDE_DIR={deps[fastfloat].path}/include",
        # "FASTFLOAT_LIBRARY={deps[fastfloat].path}/lib/libfastfloat.so",
        # "GLOG_INCLUDE_DIR={deps[glog].path}/include",
        # "GLOG_LIBRARY={deps[glog].path}/lib/libglog.so",
        # "LIBEVENT_INCLUDE_DIR={deps[libevent].path}/include",
        # "LIBEVENT_LIBRARY={deps[libevent].path}/lib/libevent.so",
        # "LIBUNWIND_INCLUDE_DIR={deps[libunwind].path}/include",
        # "LIBUNWIND_LIBRARY={deps[libunwind].path}/lib",
    ]

# Currently not building as the Folly CMake configuration
# incorrectly finds dependencies when specified this way.
# TaskRegistry.get().add_task_class(Folly)
