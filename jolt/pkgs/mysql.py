from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import boost, curl, libedit, libtirpc, lz4, openssl, rapidjson, zlib, zstd
from jolt.plugins import cmake, git, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_curl")
@attributes.requires("requires_libedit")
@attributes.requires("requires_libtirpc")
@attributes.requires("requires_lz4")
@attributes.requires("requires_ncurses")
@attributes.requires("requires_rapidjson")
@attributes.requires("requires_src")
@attributes.requires("requires_ssl")
@attributes.requires("requires_zlib")
@attributes.requires("requires_zstd")
@cmake.requires()
@cmake.use_ninja()
@pkgconfig.requires()
class MySQLBase(cmake.CMake):
    abstract = True
    version = Parameter("9.5.0", help="MySQL version.")
    requires_curl = ["curl"]
    requires_libedit = ["libedit:shared=true"]
    requires_libtirpc = ["libtirpc"]
    requires_lz4 = ["lz4"]
    requires_rapidjson = ["rapidjson"]
    requires_src = ["git:url=https://github.com/mysql/mysql-server,path={buildroot}/git-mysql,submodules=true"]
    requires_ssl = ["openssl"]
    requires_zlib = ["zlib"]
    requires_zstd = ["zstd"]
    srcdir = "{git[mysql-server]}"


class LibMySQLClient(MySQLBase):
    name = "libmysqlclient"
    shared = BooleanParameter(False, help="Build shared libraries")
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "WITH_CURL=system",
        "WITH_EDITLINE=system",
        "WITH_LZ4=system",
        "WITH_RAPIDJSON=system",
        "WITH_SSL=system",
        "WITH_UNIT_TESTS=OFF",
        "WITH_ZLIB=system",
        "WITH_ZSTD=system",
        "WITHOUT_SERVER=ON",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("mysqlclient")


TaskRegistry.get().add_task_class(LibMySQLClient)
