from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cyrus_sasl, openssl
from jolt.plugins import autotools, cxxinfo, fetch, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_libs")
@attributes.requires("requires_src")
@autotools.requires()
@pkgconfig.requires()
@cxxinfo.publish(libraries=["ldap", "lber"])
class OpenLDAP(autotools.Autotools):
    """ Lightweight Directory Access Protocol client libraries """

    name = "openldap"
    version = Parameter("2.6.16", help="OpenLDAP version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_libs = ["cyrus-sasl", "openssl"]
    """ Libraries used for SASL authentication and TLS. """
    requires_src = ["fetch:alias=src,url=https://www.openldap.org/software/download/OpenLDAP/openldap-release/openldap-{version}.tgz"]
    srcdir = "{fetch[src]}/openldap-{version}"
    options = [
        "--disable-slapd",
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
        "--localstatedir=/var",
        "--sysconfdir=/etc",
        "--with-cyrus-sasl",
        "--with-pic",
        "--with-tls=openssl",
    ]
    """ Options passed to the ``configure`` script. The configuration of the system is used at runtime. """

    def run(self, deps, tools):
        # SASL and OpenSSL are looked for with header and library checks, which ignore pkg-config
        with tools.environ(
            CPPFLAGS=tools.run("pkg-config --cflags libsasl2 openssl").strip() + " " + tools.getenv("CPPFLAGS", ""),
            LDFLAGS=tools.run("pkg-config --libs-only-L libsasl2 openssl").strip() + " " + tools.getenv("LDFLAGS", ""),
            # The static SASL library requires the libraries of its mechanisms
            LIBS=tools.run("pkg-config --libs libsasl2").strip() + " " + tools.getenv("LIBS", ""),
        ):
            super().run(deps, tools)
        # Let pkg-config find SASL and OpenSSL, which are not installed on the system.
        # A static library is useless without them, also without --static.
        requires = "Requires.private" if self.shared else "Requires"
        with tools.cwd(tools.autotools().installdir, "jolt-prefix", "lib", "pkgconfig"):
            tools.replace_in_file("ldap.pc", "Libs.private:  -lsasl2 -lssl -lcrypto", requires + ": libsasl2 openssl\nLibs.private:")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(OpenLDAP)
