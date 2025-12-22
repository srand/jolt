from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class Libxml2(cmake.CMake):
    name = "libxml2"
    version = Parameter("2.15.1", help="Libxml2 version.")

    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://gitlab.gnome.org/GNOME/libxml2.git,rev=v{version}"]
    srcdir = "{git[libxml2]}"


TaskRegistry.get().add_task_class(Libxml2)
