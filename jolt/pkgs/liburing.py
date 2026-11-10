from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import compiler
from jolt.plugins import cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.common_metadata()
@cxxinfo.publish(libraries=["uring"])
@attributes.requires("requires_compiler")
class Liburing(Task):
    """ Library for the Linux io_uring interface """

    name = "liburing"
    version = Parameter("2.15", help="liburing version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:clean=true,url=https://github.com/axboe/liburing.git,rev=liburing-{version}"]
    srcdir = "{git[liburing]}"
    """ Source directory. """

    def run(self, deps, tools):
        self.installdir = tools.builddir("install", incremental=False)
        make_args = "ENABLE_SHARED={}".format(1 if self.shared else 0)
        if self.pic:
            make_args += " LIBURING_CFLAGS=-fPIC"
        with tools.cwd(self.srcdir):
            # Configure writes config-host.{h,mak} into the source tree
            tools.run("./configure --prefix=/jolt-prefix --cc={} --cxx={}",
                      tools.getenv("CC", "gcc"), tools.getenv("CXX", "g++"))
            tools.run("make -C src {} {}", tools.make_jobs(), make_args)
            tools.run("make {} DESTDIR={installdir} install", make_args)
        if self.shared:
            with tools.cwd(self.installdir, "jolt-prefix", "lib"):
                for lib in tools.glob("liburing*.a"):
                    tools.unlink(lib)

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir, "jolt-prefix"):
            artifact.collect("*", symlinks=True)
        artifact.strings.install_prefix = "/jolt-prefix"
        # Let CMake's find_library and find_path find the package
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Liburing)
