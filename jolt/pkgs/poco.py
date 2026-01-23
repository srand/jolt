from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, ssl
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry
import os


@attributes.requires("requires_git")
@attributes.requires("requires_ssl")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Poco(cmake.CMake):
    name = "poco"
    version = Parameter("1.14.2", help="Poco version")
    shared = BooleanParameter(False, help="Build shared libraries")
    requires_git = ["git:url=https://github.com/pocoproject/poco.git,rev=poco-{version}-release"]
    requires_ssl = ["virtual/ssl"]
    srcdir = "{git[poco]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "POCO_MT=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.system == "windows":
            artifact.cxxinfo.msvcrt = "Dynamic"
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")

        with tools.cwd(artifact.path, "lib"):
            for libfile in tools.glob("*.lib"):
                libname, _ = os.path.splitext(libfile)
                artifact.cxxinfo.libraries.append(libname)
            for libfile in tools.glob("lib*.a"):
                libname, _ = os.path.splitext(libfile)
                artifact.cxxinfo.libraries.append(libname[3:])


TaskRegistry.get().add_task_class(Poco)
