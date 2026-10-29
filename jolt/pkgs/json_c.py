from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["json-c"])
class JsonC(cmake.CMake):
    """ JSON implementation in C """

    name = "json-c"
    version = Parameter("0.19", help="json-c version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_src = ["fetch:alias=src,url=https://s3.amazonaws.com/json-c_releases/releases/json-c-{version}.tar.gz"]
    srcdir = "{fetch[src]}/json-c-{version}"
    options = [
        "BUILD_APPS=OFF",
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_STATIC_LIBS={shared[OFF,ON]}",
        "BUILD_TESTING=OFF",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "DISABLE_WERROR=ON",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(JsonC)
