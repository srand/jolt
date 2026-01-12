from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
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
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("libxml2{shared[,s]}")
        else:
            artifact.cxxinfo.libraries.append("xml2")
            artifact.cxxinfo.libraries.append("m")
            artifact.cxxinfo.libraries.append("dl")


TaskRegistry.get().add_task_class(Libxml2)
