from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
class DBus(cmake.CMake):
    name = "dbus"
    version = Parameter("1.16.2", help="DBus version.")
    requires_git = ["git:url=https://gitlab.freedesktop.org/dbus/dbus.git,rev=dbus-{version}"]
    requires_cmake = ["cmake"]
    srcdir = "{git[dbus]}"


TaskRegistry.get().add_task_class(DBus)
