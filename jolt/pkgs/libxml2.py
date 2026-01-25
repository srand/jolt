from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
class Libxml2(cmake.CMake):
    name = "libxml2"
    version = Parameter("2.15.1", help="Libxml2 version.")
    shared = BooleanParameter(False, "Enable shared libraries.")
    requires_git = ["git:url=https://gitlab.gnome.org/GNOME/libxml2.git,rev=v{version}"]

    srcdir = "{git[libxml2]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "LIBXML2_WITH_ICONV=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("libxml2{shared[,s]}")
        else:
            artifact.cxxinfo.libraries.append("xml2")
            artifact.cxxinfo.libraries.append("m")
            artifact.cxxinfo.libraries.append("dl")


TaskRegistry.get().add_task_class(Libxml2)
