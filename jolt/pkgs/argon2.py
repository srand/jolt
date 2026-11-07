import platform

from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import compiler
from jolt.plugins import cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.common_metadata()
@cxxinfo.publish(libraries=["argon2"])
@attributes.requires("requires_compiler")
class Argon2(Task):
    """ Reference implementation of the Argon2 password hash """

    name = "argon2"
    version = Parameter("20190702", help="Argon2 version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:clean=true,url=https://github.com/P-H-C/phc-winner-argon2.git,rev={version}"]
    srcdir = "{git[phc-winner-argon2]}"
    """ Source directory. """

    @property
    def _make_args(self):
        # The default -march=native would tie artifacts in the shared cache to
        # the CPU of the build host. The optimized code needs SSE2, the
        # baseline of x86-64; other architectures use the reference code.
        if platform.machine().lower() in ("x86_64", "amd64"):
            opt = "OPTTARGET=x86-64"
        else:
            opt = "OPTTEST=1"
        return f"{opt} ARGON2_VERSION={self.version} PREFIX=/jolt-prefix LIBRARY_REL=lib PKGCONFIG_REL=lib"

    def run(self, deps, tools):
        self.installdir = tools.builddir("install", incremental=False)
        # The Makefile adds its flags to CFLAGS of the environment
        cflags = "-fPIC " if self.pic else ""
        with tools.cwd(self.srcdir), tools.environ(CFLAGS=cflags + tools.getenv("CFLAGS", "")):
            tools.run("make {} {_make_args} libs argon2", tools.make_jobs())
            tools.run("make {_make_args} DESTDIR={installdir} install")
        with tools.cwd(self.installdir, "jolt-prefix", "lib"):
            # Both kinds of libraries are always built
            for lib in tools.glob("libargon2.a" if self.shared else "libargon2.so*") + \
                    ([] if self.shared else tools.glob("libargon2*.dylib")):
                tools.unlink(lib)

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir, "jolt-prefix"):
            artifact.collect("*", symlinks=True)
        artifact.strings.install_prefix = "/jolt-prefix"
        # Let CMake's find_library and find_path find the package
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Argon2)
