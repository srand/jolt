from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake, compiler, libogg
from jolt.plugins import cxxinfo, git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ogg")
@cmake.requires()
@cmake.use_ninja()
@pkgconfig.requires()
@cxxinfo.publish(libraries=["vorbis", "vorbisenc", "vorbisfile"])
@attributes.requires("requires_compiler")
class Libvorbis(cmake.CMake):
    name = "libvorbis"
    version = Parameter("1.3.7", help="libvorbis version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/xiph/vorbis.git,rev=v{version}"]
    requires_ogg = ["libogg"]
    srcdir = "{git[vorbis]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
    ]


TaskRegistry.get().add_task_class(Libvorbis)
