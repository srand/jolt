from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, perl, ssl
from jolt.plugins import autotools, cxxinfo, fetch, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_perl")
@attributes.requires("requires_src")
@attributes.requires("requires_ssl_{ssl[on,off]}")
@pkgconfig.requires()
@cxxinfo.publish(libraries=["pq"])
@attributes.requires("requires_compiler")
class Libpq(autotools.Autotools):
    """ C client library of PostgreSQL """

    name = "libpq"
    version = Parameter("18.6", help="PostgreSQL version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    ssl = BooleanParameter(True, help="Enable SSL support.")
    requires_compiler = ["virtual/compiler/c"]
    requires_perl = ["virtual/perl"]
    requires_ssl_on = ["virtual/ssl:shared={shared}"]
    # Git checkouts lack the generated parsers, which need bison and flex
    requires_src = ["fetch:alias=src,url=https://ftp.postgresql.org/pub/source/v{version}/postgresql-{version}.tar.bz2"]
    srcdir = "{fetch[src]}/postgresql-{version}"
    # Features of the server and the tools, which would use libraries of the
    # build host, are disabled.
    options = [
        "--disable-nls",
        "--with-ssl={ssl[openssl,no]}",
        "--without-gssapi",
        "--without-icu",
        "--without-ldap",
        "--without-lz4",
        "--without-readline",
        "--without-zlib",
        "--without-zstd",
    ]

    def run(self, deps, tools):
        # OpenSSL is looked for with header and library checks, which ignore pkg-config
        flags = {}
        if self.ssl:
            flags = dict(
                CPPFLAGS=tools.run("pkg-config --cflags openssl", output=False).strip() + " " + tools.getenv("CPPFLAGS", ""),
                LDFLAGS=tools.run("pkg-config --libs-only-L openssl", output=False).strip() + " " + tools.getenv("LDFLAGS", ""),
            )
        at = tools.autotools(deps, incremental=self.incremental)
        with tools.environ(**flags):
            at.configure(self.srcdir, *tools.expand(self.options))
        # Only the client library, its headers and pg_config. The static
        # library needs the common and port libraries of PostgreSQL.
        for subdir in ["src/include", "src/common", "src/port", "src/interfaces/libpq", "src/bin/pg_config"]:
            if subdir == "src/interfaces/libpq":
                # A check rejects libraries that reference functions named
                # *exit, but static OpenSSL brings in pthread_exit.
                at.build("-C", subdir, "all-lib")
                tools.write_file(f"{at.builddir}/{subdir}/libpq-refs-stamp", "")
            else:
                at.build("-C", subdir)
            at.install(f"-C {subdir} install")

        with tools.cwd(at.installdir, "jolt-prefix", "lib"):
            if not self.shared:
                for lib in tools.glob("libpq.so*") + tools.glob("libpq.*dylib"):
                    tools.unlink(lib)
            # Let pkg-config find OpenSSL, which is not installed on the system,
            # instead of the path to it at build time. The static library is
            # useless without its dependencies, also without --static.
            with tools.cwd("pkgconfig"):
                requires = "Requires.private" if self.shared else "Requires"
                tools.replace_in_file("libpq.pc", r"Requires: *\nRequires\.private:.*", requires + ": {ssl[openssl,]}", regex=True)
                tools.replace_in_file("libpq.pc", r"(Libs\.private:.*?) -L\S+", r"\1", regex=True)
                tools.replace_in_file("libpq.pc", r"(Libs\.private:.*?) -lssl", r"\1", regex=True)
                tools.replace_in_file("libpq.pc", r"(Libs\.private:.*?) -lcrypto", r"\1", regex=True)
                if not self.shared:
                    # libpq is compiled against the variants of the common and
                    # port libraries for shared libraries, which keep the names
                    # of the functions that the others rename
                    tools.replace_in_file("libpq.pc", "\nLibs.private:", "")
                    tools.replace_in_file("libpq.pc", "-lpgcommon -lpgport", "-lpgcommon_shlib -lpgport_shlib")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("bin")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")
        else:
            artifact.cxxinfo.libraries.append("pgcommon_shlib")
            artifact.cxxinfo.libraries.append("pgport_shlib")


TaskRegistry.get().add_task_class(Libpq)
