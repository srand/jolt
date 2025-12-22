from jolt import attributes, Parameter
from jolt.pkgs import boost, cmake, sqlite
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_boost")
@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@attributes.requires("requires_sqlite")
class Soci(cmake.CMake):
    name = "soci"
    version = Parameter("4.1.2", help="soci version.")
    requires_boost = ["boost"]
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/SOCI/soci.git,rev=v{version}"]
    requires_sqlite = ["sqlite"]
    srcdir = "{git[soci]}"


TaskRegistry.get().add_task_class(Soci)
