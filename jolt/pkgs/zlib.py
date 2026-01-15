from jolt import attributes, Alias, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class Zlib(cmake.CMake):
    name = "zlib"
    version = Parameter("1.3.1", help="Zlib version.")
    shared = BooleanParameter(False, "Enable shared libraries.")
    requires_git = ["git:clean=true,url=https://github.com/madler/zlib.git,rev=v{version}"]
    srcdir = "{git[zlib]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "ZLIB_BUILD_EXAMPLES=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.system == "windows":
            self.publish_windows(artifact, tools)
        else:
            self.publish_unix(artifact, tools)

    def publish_unix(self, artifact, tools):
        artifact.cxxinfo.libraries.append("z")
        with tools.cwd(artifact.path, "lib"):
            if self.shared:
                for lib in tools.glob("*.a"):
                    tools.unlink(lib)
            else:
                for lib in tools.glob("*.so*") + tools.glob("*.dylib*"):
                    tools.unlink(lib)

    def publish_windows(self, artifact, tools):
        with tools.cwd(artifact.path, "lib"):
            if self.shared:
                artifact.cxxinfo.libraries.append("zlib")
                for lib in tools.glob("zlibstatic.*"):
                    tools.unlink(lib)
            else:
                artifact.cxxinfo.libraries.append("zlibstatic")
                for lib in tools.glob("zlib.*"):
                    tools.unlink(lib)


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class ZlibNg(cmake.CMake):
    name = "zlib-ng"
    version = Parameter("2.3.2", help="Zlib version.")
    shared = BooleanParameter(False, "Enable shared libraries.")
    requires_git = ["git:url=https://github.com/zlib-ng/zlib-ng.git,rev={version}"]
    srcdir = "{git[zlib-ng]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_TESTING=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("zlibstatic-ng")
        else:
            artifact.cxxinfo.libraries.append("z-ng")


class VirtualZlib(Alias):
    name = "virtual/zlib"
    requires = ["zlib"]


TaskRegistry.get().add_task_class(Zlib)
TaskRegistry.get().add_task_class(ZlibNg)
TaskRegistry.get().add_task_class(VirtualZlib)
