from jolt import attributes, Parameter
from jolt.pkgs import cmake, openssl
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@attributes.requires("requires_ssl")
class Poco(cmake.CMake):
    name = "poco"
    version = Parameter("1.14.2", help="poco version.")
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/pocoproject/poco.git,rev=poco-{version}-release"]
    requires_ssl = ["openssl"]
    srcdir = "{git[poco]}"


TaskRegistry.get().add_task_class(Poco)
