from jolt import attributes, Parameter
from jolt.plugins import git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@pkgconfig.cxxinfo(["sqlite3"])
class SQLite(autotools.Autotools):
    name = "sqlite"
    version = Parameter("3.51.1", help="sqlite version.")
    requires_git = ["git:url=https://github.com/sqlite/sqlite.git,rev=version-{version}"]
    srcdir = "{git[sqlite]}"


TaskRegistry.get().add_task_class(SQLite)
