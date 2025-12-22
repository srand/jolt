from jolt import attributes, Parameter
from jolt.pkgs import cmake, libxml2
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libxml2")
class Libxslt(cmake.CMake):
    name = "libxslt"
    version = Parameter("1.1.45", help="libxslt version.")
    requires_git = ["git:url=https://gitlab.gnome.org/GNOME/libxslt.git,rev=v{version}"]
    requires_libxml2 = ["libxml2"]
    srcdir = "{git[libxslt]}"


TaskRegistry.get().add_task_class(Libxslt)
