from jolt import attributes, Parameter, Task
from jolt.pkgs import gcc
from jolt.plugins import git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_{_variant}")
@attributes.requires("requires_compiler")
class Musl(Task):
    """
    musl C library

    The library is installed as a system root, with headers in usr/include and
    libraries in usr/lib. It is built for the host with the host compiler, or
    for a target with the cross compiler for that target.
    """

    name = "musl"
    version = Parameter("1.2.6", help="musl version.")
    target = Parameter(required=False, help="Target of the library, such as aarch64-linux-musl. The host if not set.")
    requires_compiler = ["compiler/c"]
    requires_cross = ["gcc:target={target}"]
    """ Cross compiler for the target. """
    requires_git = ["git:clean=true,url=https://git.musl-libc.org/git/musl,rev=v{version}"]
    requires_native = []
    """ The host compiler is used. """
    srcdir = "{git[musl]}"
    selfsustained = True
    """ Consumers of the library don't need the compiler that built it. """

    @property
    def _variant(self):
        return "cross" if self.target.is_set() else "native"

    def run(self, deps, tools):
        self.installdir = tools.builddir("install")
        builddir = tools.builddir("build", incremental=True)
        target = tools.expand("--target={target} CROSS_COMPILE={target}-") if self._variant == "cross" else ""
        srcdir = tools.expand_path(self.srcdir)
        with tools.cwd(builddir):
            tools.run("{}/configure --prefix=/usr --syslibdir=/lib {}", srcdir, target)
            tools.run("make {}", tools.make_jobs())
            tools.run("make DESTDIR={installdir} install")
        # The dynamic linker is installed as an absolute link to the library
        with tools.cwd(self.installdir, "lib"):
            for linker in tools.glob("ld-musl-*"):
                tools.symlink("../usr/lib/libc.so", linker)

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.paths.sysroot = "."


TaskRegistry.get().add_task_class(Musl)
