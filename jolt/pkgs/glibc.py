from jolt import attributes, Parameter, Task
from jolt.pkgs import bison, compiler, gcc, linux_headers
from jolt.plugins import fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@attributes.requires("requires_tools")
@attributes.requires("requires_{_variant}")
@attributes.requires("requires_compiler")
class Glibc(Task):
    """
    GNU C library

    The library is installed as a system root, with headers in usr/include and
    libraries in usr/lib. It is built for the host with the host compiler, or
    for a target with the cross compiler for that target.
    """

    name = "glibc"
    version = Parameter("2.44", help="GNU C Library version.")
    target = Parameter(required=False, help="Target of the library, such as aarch64-linux-gnu. The host if not set.")
    requires_compiler = ["compiler/c"]
    requires_cross = ["gcc:target={target}", "linux-headers:target={target}"]
    """ Cross compiler and kernel headers of the target. """
    requires_native = ["linux-headers"]
    """ Kernel headers of the host. The host compiler is used. """
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/glibc/glibc-{version}.tar.xz"]
    requires_tools = ["bison"]
    """ Tools used to build the library. """
    srcdir = "{fetch[src]}/glibc-{version}"
    selfsustained = True
    """ Consumers of the library don't need the compiler that built it. """

    @property
    def _variant(self):
        return "cross" if self.target.is_set() else "native"

    def run(self, deps, tools):
        self.installdir = tools.builddir("install")
        builddir = tools.builddir("build", incremental=True)
        headers = deps[tools.expand("linux-headers:target={target}") if self._variant == "cross" else "linux-headers"].path
        # The cross compiler has no libatomic, which GCC links with by default
        host = tools.expand("--host={target} CC='{target}-gcc -fno-link-libatomic'") if self._variant == "cross" else ""
        srcdir = tools.expand_path(self.srcdir)
        with tools.cwd(builddir):
            tools.run(
                "{}/configure --prefix=/usr {} --with-headers={}/usr/include "
                "--disable-werror --enable-kernel=4.4 --without-selinux libc_cv_slibdir=/usr/lib",
                srcdir, host, headers)
            tools.run("make {}", tools.make_jobs())
            tools.run("make DESTDIR={installdir} install")
        # The kernel headers are part of the system root
        tools.run("cp -a {}/usr/include/. {installdir}/usr/include/", headers)
        # Programs look for the dynamic linker in /lib
        tools.symlink("usr/lib", "{installdir}/lib")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.paths.sysroot = "."


TaskRegistry.get().add_task_class(Glibc)
