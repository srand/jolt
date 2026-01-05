from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class PugiXML(cmake.CMake):
    name = "pugixml"
    version = Parameter("1.15", help="PugiXML version.")
    requires_git = ["git:url=https://github.com/zeux/pugixml.git,rev=v{version}"]
    srcdir = "{git[pugixml]}"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("pugixml")


TaskRegistry.get().add_task_class(PugiXML)
