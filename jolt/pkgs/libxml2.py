from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@pkgconfig.to_cxxinfo(["libxml-2.0"])
class Libxml2(cmake.CMake):
    name = "libxml2"
    version = Parameter("2.15.1", help="Libxml2 version.")
    requires_git = ["git:url=https://gitlab.gnome.org/GNOME/libxml2.git,rev=v{version}"]
    srcdir = "{git[libxml2]}"
    options = ["LIBXML2_WITH_ICONV=OFF"]
    


TaskRegistry.get().add_task_class(Libxml2)
