from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import nasm, perl
from jolt.plugins import git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_perl")
@attributes.requires("requires_{system}_nasm")
@attributes.common_metadata()
@attributes.system
class OpenSSL(Task):
    name = "openssl"
    version = Parameter("3.6.0", help="openssl version.")
    shared = BooleanParameter(False, "Enable shared libraries.")

    requires_git = ["git:url=https://github.com/openssl/openssl.git,rev=openssl-{version}"]
    requires_perl = ["virtual/perl"]
    requires_windows_nasm = ["nasm"]

    def clean(self):
        pass

    def run(self, deps, tools):
        self.builddir = tools.builddir(incremental=True)
        self.installdir = tools.builddir("install")
        self.srcdir = tools.expand_path("{git[openssl]}")
        with tools.cwd(self.builddir):
            self.info("Configuring OpenSSL... {builddir}")

            if self.system == "windows":
                tools.run("perl {srcdir}/Configure --prefix={installdir} --openssldir=ssl no-tests {shared[,no-shared]}")
                tools.run("nmake")
                tools.run("nmake install")
            else:
                tools.run("{srcdir}/config --prefix={installdir} no-tests {shared[,no-shared]}")
                tools.run("make -j{}", tools.cpu_count())
                tools.run("make install")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("ssl")
        artifact.cxxinfo.libraries.append("crypto")
        artifact.strings.install_prefix = self.installdir
        if self.system == "windows":
            self.publish_pkgconfig(artifact, tools)

    def publish_pkgconfig(self, artifact, tools):
        with tools.tmpdir() as tmp, tools.cwd(tmp):
            tools.write_file(
                "openssl.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/lib
includedir=${{prefix}}/include

Name: OpenSSL
Description: Secure Sockets Layer and cryptography libraries and tools
Version: {version}-{identity}
Requires: libssl libcrypto
""")
            tools.write_file(
                "libcrypto.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/lib
includedir=${{prefix}}/include
enginesdir=${{libdir}}/engines-3

Name: OpenSSL-libcrypto
Description: OpenSSL cryptography library
Version: {version}-{identity}
Libs: -L${{libdir}} -lcrypto
Cflags: -I${{includedir}}
""")
            tools.write_file(
                "libssl.pc",
                """
# See: man pkg-config
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}/bin
libdir=${{prefix}}/lib
includedir=${{prefix}}/include

Name: OpenSSL-libssl
Description: Secure Sockets Layer and cryptography libraries
Version: {version}-{identity}
Libs: -L${{libdir}} -lssl
Cflags: -I${{includedir}}
""")
            artifact.collect("openssl.pc", "lib/pkgconfig/")
            artifact.collect("libcrypto.pc", "lib/pkgconfig/")
            artifact.collect("libssl.pc", "lib/pkgconfig/")


TaskRegistry.get().add_task_class(OpenSSL)
