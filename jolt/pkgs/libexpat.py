from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["expat"])
class Libexpat(cmake.CMake):
    name = "libexpat"
    version = Parameter("2.7.3", help="Expat version.")
    shared = BooleanParameter(False, help="Build shared libraries")
    version_tag = property(lambda self: str(self.version).replace('.', '_'))
    requires_src = ["fetch:alias=src,url=https://github.com/libexpat/libexpat/releases/download/R_{version_tag}/expat-{version}.tar.gz"]
    srcdir = "{fetch[src]}/expat-{version}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(Libexpat)
