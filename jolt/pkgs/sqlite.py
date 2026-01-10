from jolt import BooleanParameter, attributes, Alias, Parameter, Task
from jolt.plugins import git, autotools
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires()
class SQLitePosix(autotools.Autotools):
    name = "sqlite/src/posix"
    version = Parameter("3.51.1", help="sqlite version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["git:url=https://github.com/sqlite/sqlite.git,rev=version-{version}"]
    srcdir = "{git[sqlite]}"
    options = [
        "--{shared[enable,disable]}-shared",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        with tools.cwd(self.srcdir):
            artifact.cxxinfo.incpaths.append("include")
            artifact.cxxinfo.libpaths.append("lib")
            artifact.cxxinfo.libraries.append("sqlite3")


@attributes.common_metadata()
@attributes.requires("requires_git")
class SQLiteWin32(Task):
    name = "sqlite/src/win32"
    version = Parameter("3.51.1", help="sqlite version.")
    shared = BooleanParameter(True, help="Build shared libraries.")
    requires_git = ["git:clean=true,url=https://github.com/sqlite/sqlite.git,rev=version-{version}"]
    srcdir = "{git[sqlite]}"

    def run(self, deps, tools):
        self.srcdir = tools.expand_path(self.srcdir)
        with tools.cwd(self.srcdir):
            tools.run("nmake -f Makefile.msc sqlite3.exe sqlite3.dll")
            tools.write_file(
                "sqlite3.pc",
                """
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/lib
includedir=${{prefix}}/include

Name: SQLite
Description: SQL database engine
Version: {version}-{identity}
Libs: -L${{libdir}} -lsqlite3
Cflags: -I${{includedir}}
""")

    def publish(self, artifact, tools):
        with tools.cwd(self.srcdir):
            if self.shared:
                artifact.collect("sqlite3.dll", "bin/")
                artifact.collect("sqlite3.lib", "lib/")
            else:
                artifact.collect("libsqlite3.lib", "lib/")
            artifact.collect("sqlite3.exe", "bin/")
            artifact.collect("sqlite*.h", "include/")
            artifact.collect("sqlite3.pc", "lib/pkgconfig/")
            artifact.cxxinfo.incpaths.append("include")
            artifact.cxxinfo.libpaths.append("lib")
            artifact.cxxinfo.libraries.append("sqlite3")
            artifact.environ.CMAKE_PREFIX_PATH.append(".")


@attributes.requires("requires_{system}")
@attributes.system
class SQLite(Alias):
    name = "sqlite"
    version = Parameter("3.51.1", help="sqlite version.")
    requires_darwin = ["sqlite/src/posix:version={version}"]
    requires_linux = requires_darwin
    requires_windows = ["sqlite/src/win32:version={version}"]


TaskRegistry.get().add_task_class(SQLite)
TaskRegistry.get().add_task_class(SQLitePosix)
TaskRegistry.get().add_task_class(SQLiteWin32)
