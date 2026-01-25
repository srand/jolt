from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, ssl
from jolt.plugins import cxxinfo, git, cmake
from jolt.tasks import TaskRegistry
import os


@attributes.requires("requires_git")
@attributes.requires("requires_ssl")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
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

        for libdir in ["lib", "lib32", "lib64"]:
            full_libdir = os.path.join(artifact.path, libdir)
            if not os.path.isdir(full_libdir):
                continue
            with tools.cwd(artifact.path, libdir):
                for libfile in tools.glob("*.lib"):
                    libname, _ = os.path.splitext(libfile)
                    artifact.cxxinfo.libraries.append(libname)
                for libfile in tools.glob("lib*.a"):
                    libname, _ = os.path.splitext(libfile)
                    artifact.cxxinfo.libraries.append(libname[3:])


TaskRegistry.get().add_task_class(Poco)
