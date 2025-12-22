from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class PugiXML(cmake.CMake):
    name = "pugixml"
    version = Parameter("1.15", help="PugiXML version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/zeux/pugixml.git,rev=v{version}"]
    srcdir = "{git[pugixml]}"


TaskRegistry.get().add_task_class(PugiXML)
