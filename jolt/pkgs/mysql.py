from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import boost, curl, libtirpc, openssl, rapidjson, zlib, zstd
from jolt.plugins import cmake, fetch, git, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@attributes.requires("requires_curl")
@attributes.requires("requires_libtirpc")
@attributes.requires("requires_rapidjson")
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
    requires_libtirpc = ["libtirpc"]
    requires_rapidjson = ["rapidjson"]
    requires_src = ["fetch:alias=src,url=https://github.com/mysql/mysql-server/archive/refs/tags/mysql-9.5.0.tar.gz"]
    requires_ssl = ["openssl"]
    requires_zlib = ["zlib"]
    requires_zstd = ["zstd"]
    srcdir = "{fetch[src]}/mysql-server-mysql-{version}"


class LibMySQLClient(MySQLBase):
    name = "libmysqlclient"
    shared = BooleanParameter(False, help="Build shared libraries")
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "WITH_CURL=system",
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
