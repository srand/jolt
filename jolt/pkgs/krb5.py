from jolt import attributes, Parameter
from jolt.pkgs import bison, compiler
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_bison")
@attributes.requires("requires_src")
@attributes.system
@autotools.options("options_{system}")
@cxxinfo.publish(libraries=["gssapi_krb5", "krb5", "k5crypto", "com_err"])
@attributes.requires("requires_compiler")
class Krb5(autotools.Autotools):
    """ MIT Kerberos """

    name = "krb5"
    version = Parameter("1.22.2", help="MIT Kerberos version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_bison = ["bison"]
    requires_src = ["fetch:alias=src,url=https://kerberos.org/dist/krb5/{_major_minor}/krb5-{version}.tar.gz"]
    srcdir = "{fetch[src]}/krb5-{version}/src"
    options = [
        # The C23 versions of string functions in glibc return const pointers,
        # which krb5 treats as an error
        "krb5_cv_cc_flag__dash_Werror_eq_discarded_dash_qualifiers=no",
        # The libraries would find each other in the installation prefix
        "--disable-rpath",
        "--localstatedir=/var",
        "--sysconfdir=/etc",
        "--with-crypto-impl=builtin",
        "--with-tls-impl=no",
        "--without-keyutils",
        "--without-libedit",
        "--without-lmdb",
    ]
    """ Options passed to the ``configure`` script. The configuration of the system is used at runtime. """
    options_darwin = [
        # The tools define variables that the static libraries also define
        "CFLAGS='-O2 -fcommon'",
        # The macOS credential cache of the static libkrb5 calls the Kerberos
        # framework, which only the shared libraries link with
        "LIBS='-framework Kerberos'",
        "--disable-shared",
        "--enable-static",
    ]
    """
    Static libraries: the install names of the shared libraries on macOS are in
    /jolt-prefix, and programs linked with them can't load them, also those that
    configure runs.
    """

    @property
    def _major_minor(self):
        return ".".join(str(self.version).split(".")[:2])

    def run(self, deps, tools):
        super().run(deps, tools)
        # The prefix in krb5-config must follow the artifact when it is relocated
        with tools.cwd(tools.autotools().installdir, "jolt-prefix", "bin"):
            tools.replace_in_file("krb5-config", "prefix=/jolt-prefix", 'prefix="$(cd "$(dirname "$0")/.." && pwd)"')
        if self.system == "darwin":
            # Consumers of the static libraries must link the libraries they require
            with tools.cwd(tools.autotools().installdir, "jolt-prefix", "bin"):
                tools.replace_in_file("krb5-config", '-lkrb5 -lk5crypto -lcom_err"', '-lkrb5 -lk5crypto -lcom_err -lkrb5support $LIBS $DL_LIB"')
            with tools.cwd(tools.autotools().installdir, "jolt-prefix", "lib", "pkgconfig"):
                tools.replace_in_file("mit-krb5-gssapi.pc", "Requires.private:", "Requires:")
                tools.replace_in_file("mit-krb5.pc", "\nLibs.private: -lkrb5support", " -lkrb5support -lresolv -framework Kerberos")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Krb5)
