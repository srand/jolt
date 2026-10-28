from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["tbb", "tbbmalloc"])
class OneTbb(cmake.CMake):
    """ oneAPI Threading Building Blocks, a library for task parallelism """

    name = "onetbb"
    version = Parameter("2023.2.0", help="oneTBB version.")
    shared = BooleanParameter(True, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/uxlfoundation/oneTBB.git,rev=v{version}"]
    srcdir = "{git[oneTBB]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        # TBBBind would use hwloc from the host
        "TBB_DISABLE_HWLOC_AUTOMATIC_SEARCH=ON",
        "TBB_STRICT=OFF",
        "TBB_TEST=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(OneTbb)
