from jolt import attributes, Parameter, Task
from jolt.pkgs import gcc
from jolt.plugins import git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_{_variant}")
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
    requires_cross = ["gcc:target={target}"]
    """ Cross compiler for the target. """
    requires_git = ["git:clean=true,url=https://git.musl-libc.org/git/musl,rev=v{version}"]
    requires_native = []
    """ The host compiler is used. """
    srcdir = "{git[musl]}"

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
            tools.run("make -j{}", tools.cpu_count())
            tools.run("make DESTDIR={installdir} install")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            artifact.collect("*", symlinks=True)
        artifact.paths.sysroot = "."


TaskRegistry.get().add_task_class(Musl)
