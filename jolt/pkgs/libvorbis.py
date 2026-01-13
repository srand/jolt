from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, libogg
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ogg")
@cmake.requires()
@cmake.use_ninja()
@pkgconfig.requires()
class Libvorbis(cmake.CMake):
    name = "libvorbis"
    version = Parameter("1.3.7", help="libvorbis version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/xiph/vorbis.git,rev=v{version}"]
    requires_ogg = ["libogg"]
    srcdir = "{git[vorbis]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("vorbis")
        artifact.cxxinfo.libraries.append("vorbisenc")
        artifact.cxxinfo.libraries.append("vorbisfile")


TaskRegistry.get().add_task_class(Libvorbis)
