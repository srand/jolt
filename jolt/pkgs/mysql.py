from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import boost, curl, cyrus_sasl, krb5, libedit, libtirpc, libudev_zero, lz4, openldap, openssl, rapidjson, zlib, zstd
from jolt.plugins import cmake, cxxinfo, git, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_curl")
@attributes.requires("requires_{system}_krb5")
@attributes.requires("requires_{system}_ldap")
@attributes.requires("requires_{system}_libedit")
@attributes.requires("requires_{system}_libtirpc")
@attributes.requires("requires_{system}_libudev")
@attributes.requires("requires_lz4")
@attributes.requires("requires_ncurses")
@attributes.requires("requires_rapidjson")
@attributes.requires("requires_src")
@attributes.requires("requires_ssl")
@attributes.requires("requires_zlib")
@attributes.requires("requires_zstd")
@attributes.system
@cmake.options("_options_{system}")
@cmake.requires()
@cmake.use_ninja()
@pkgconfig.requires()
class MySQLBase(cmake.CMake):
    abstract = True
    version = Parameter("26.10.0", help="MySQL version.")
    requires_curl = ["curl"]
    requires_darwin_libedit = ["libedit:shared=true"]
    requires_linux_krb5 = ["krb5"]
    # Required by the LDAP authentication plugins
    requires_linux_ldap = ["cyrus-sasl", "openldap"]
    requires_linux_libedit = requires_darwin_libedit
    requires_linux_libtirpc = ["libtirpc"]
    # Required by libfido2 for WebAuthn authentication
    requires_linux_libudev = ["libudev-zero"]
    requires_lz4 = ["lz4"]
    requires_rapidjson = ["rapidjson"]
    requires_src = ["git:url=https://github.com/mysql/mysql-server,path={buildroot}/git-mysql,rev=mysql-{version},submodules=true"]
    requires_ssl = ["openssl"]
    requires_zlib = ["zlib"]
    requires_zstd = ["zstd"]
    srcdir = "{git[mysql-server]}"

    @property
    def _options_linux(self):
        """
        LDAP from its package, which the search of the system would miss, and the
        libraries of the static SASL library, which MySQL doesn't link with.
        """
        sasl_libs = self.tools.run("pkg-config --libs libsasl2", output=False).strip()
        return [
            "CMAKE_C_STANDARD_LIBRARIES='{}'".format(sasl_libs),
            "CMAKE_CXX_STANDARD_LIBRARIES='{}'".format(sasl_libs),
            "WITH_LDAP=" + self.tools.run("pkg-config --variable=prefix ldap", output=False).strip(),
        ]

    def run(self, deps, tools):
        if self.system != "linux":
            return super().run(deps, tools)
        # libudev.h and sasl/sasl.h are looked for with check_include_file, which ignores pkg-config
        cflags = tools.run("pkg-config --cflags libudev libsasl2").strip()
        with tools.environ(
            CFLAGS=cflags + " " + tools.getenv("CFLAGS", ""),
            CXXFLAGS=cflags + " " + tools.getenv("CXXFLAGS", ""),
        ):
            super().run(deps, tools)


@cxxinfo.publish(libraries=["mysqlclient"])
class LibMySQLClient(MySQLBase):
    name = "libmysqlclient"
    shared = BooleanParameter(False, help="Build shared libraries.")
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


TaskRegistry.get().add_task_class(LibMySQLClient)
