from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class Libogg(cmake.CMake):
    name = "libogg"
    version = Parameter("1.3.6", help="libogg version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/xiph/ogg.git,rev=v{version}"]
    srcdir = "{git[ogg]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("ogg")


TaskRegistry.get().add_task_class(Libogg)
