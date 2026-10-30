from jolt import attributes, Parameter
from jolt.pkgs import compiler, krb5, openssl
from jolt.plugins import autotools, cxxinfo, fetch, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_libs")
@attributes.requires("requires_src")
@autotools.requires()
@pkgconfig.requires()
@cxxinfo.publish(libraries=["sasl2"])
@attributes.requires("requires_compiler")
class CyrusSasl(autotools.Autotools):
    """
    Simple Authentication and Security Layer library

    Only a static library is built, with the authentication mechanisms
    included, so that no plugins are loaded from the installation directory.
    """

    name = "cyrus-sasl"
    version = Parameter("2.1.28", help="Cyrus SASL version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_libs = ["krb5", "openssl"]
    """ Libraries used by the GSSAPI and other mechanisms. """
    requires_src = ["fetch:alias=src,url=https://github.com/cyrusimap/cyrus-sasl/releases/download/cyrus-sasl-{version}/cyrus-sasl-{version}.tar.gz"]
    srcdir = "{fetch[src]}/cyrus-sasl-{version}"
    options = [
        "--disable-macos-framework",
        "--disable-sample",
        "--disable-shared",
        "--enable-gssapi",
        "--enable-static",
        "--with-configdir=/etc/sasl2",
        "--with-pic",
        "--without-authdaemond",
        "--without-saslauthd",
    ]
    """ Options passed to the ``configure`` script. The configuration of the system is used at runtime. """

    def run(self, deps, tools):
        # The built-in mechanisms are only registered in code that isn't position
        # independent, which is taken to mean a static library
        with tools.cwd(self.srcdir):
            tools.replace_in_file(
                "lib/dlopen.c",
                '#include "saslint.h"\n\n#ifndef PIC\n',
                '#include "saslint.h"\n\n#undef PIC\n#ifndef PIC\n')
        # OpenSSL is looked for with header and library checks, which ignore pkg-config.
        # The code predates C23, and cram.c lacks a declaration of time(). The
        # built-in mechanisms are compiled without libtool, which adds -fPIC.
        with tools.environ(
            CFLAGS="-O2 -fPIC -std=gnu17 -Wno-error=implicit-function-declaration " + tools.getenv("CFLAGS", ""),
            CPPFLAGS=tools.run("pkg-config --cflags openssl").strip() + " " + tools.getenv("CPPFLAGS", ""),
            LDFLAGS=tools.run("pkg-config --libs-only-L openssl").strip() + " " + tools.getenv("LDFLAGS", ""),
            # The utilities link with the built-in mechanisms and their libraries
            LIBS=tools.run("pkg-config --libs krb5-gssapi libcrypto").strip() + " " + tools.getenv("LIBS", ""),
        ):
            super().run(deps, tools)
        # The static library includes the mechanisms, which require these libraries
        with tools.cwd(tools.autotools().installdir, "jolt-prefix", "lib", "pkgconfig"):
            tools.replace_in_file("libsasl2.pc", "Libs.private:", "Requires: krb5-gssapi libcrypto\nLibs.private:")

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(CyrusSasl)
