from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, compiler
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["pugixml"])
@attributes.requires("requires_compiler")
class PugiXML(cmake.CMake):
    name = "pugixml"
    version = Parameter("1.16", help="pugixml version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/zeux/pugixml.git,rev=v{version}"]
    srcdir = "{git[pugixml]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(PugiXML)
