from jolt import attributes, Parameter
from jolt.pkgs import cmake, libogg
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ogg")
@cmake.requires()
class Libvorbis(cmake.CMake):
    name = "libvorbis"
    version = Parameter("1.3.7", help="libvorbis version.")
    options = ["CMAKE_POLICY_VERSION_MINIMUM=3.5"]
    requires_git = ["git:url=https://github.com/xiph/vorbis.git,rev=v{version}"]
    requires_ogg = ["libogg"]
    srcdir = "{git[vorbis]}"


TaskRegistry.get().add_task_class(Libvorbis)
