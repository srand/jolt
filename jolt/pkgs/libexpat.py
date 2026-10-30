from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import cmake, cxxinfo, fetch, git
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler


@attributes.requires("requires_src")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["expat"])
@attributes.requires("requires_compiler")
class Libexpat(cmake.CMake):
    name = "libexpat"
    version = Parameter("2.9.0", help="Expat version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    version_tag = property(lambda self: str(self.version).replace('.', '_'))
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://github.com/libexpat/libexpat/releases/download/R_{version_tag}/expat-{version}.tar.gz"]
    srcdir = "{fetch[src]}/expat-{version}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(Libexpat)
