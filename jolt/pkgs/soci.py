from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import boost, cmake, mysql, sqlite
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_boost_{boost[on,off]}")
@attributes.requires("requires_git")
@attributes.requires("requires_mysql_{mysql[on,off]}")
@attributes.requires("requires_sqlite_{sqlite[on,off]}")
@cmake.requires()
@cmake.use_ninja()
class Soci(cmake.CMake):
    name = "soci"
    version = Parameter("4.1.2", help="Soci version")
    shared = BooleanParameter(False, help="Build shared libraries")
    boost = BooleanParameter(False, help="Enable boost support")
    mysql = BooleanParameter(True, help="Enable MySQL support")
    sqlite = BooleanParameter(True, help="Enable sqlite support")

    requires_boost_on = ["boost"]
    requires_git = ["git:url=https://github.com/SOCI/soci.git,rev=v{version}"]
    requires_mysql_on = ["libmysqlclient"]
    requires_sqlite_on = ["sqlite"]
    srcdir = "{git[soci]}"
    options = [
        "SOCI_TESTS=OFF",
        "SOCI_SHARED={shared[ON,OFF]}",
        "SOCI_SQLITE3={sqlite[ON,OFF]}",
        "SOCI_MYSQL={mysql[ON,OFF]}",
        "WITH_BOOST={boost[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.sqlite:
            artifact.cxxinfo.libraries.append("soci_sqlite3")
        if self.mysql:
            artifact.cxxinfo.libraries.append("soci_mysql")
        artifact.cxxinfo.libraries.append("soci_odbc")
        artifact.cxxinfo.libraries.append("soci_core")


TaskRegistry.get().add_task_class(Soci)
