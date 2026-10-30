from jolt import attributes, Parameter, Task
from jolt.plugins import cxxinfo, git
from jolt.tasks import BooleanParameter, TaskRegistry
from jolt.pkgs import compiler


@attributes.common_metadata()
@attributes.requires("requires_git")
@cxxinfo.publish(libraries=["udev"])
@attributes.requires("requires_compiler")
class LibudevZero(Task):
    """ Daemonless replacement for libudev """

    name = "libudev-zero"
    version = Parameter("1.0.5", help="libudev-zero version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:clean=true,url=https://github.com/illiliti/libudev-zero.git,rev={version}"]
    srcdir = "{git[libudev-zero]}"
    """ Source directory. """

    def run(self, deps, tools):
        self.installdir = tools.builddir("install")
        with tools.cwd(self.srcdir):
            tools.run("make {} {shared[libudev.so.1,libudev.a]} libudev.pc PREFIX=/jolt-prefix "
                      "USB_IDS_PATH=/usr/share/hwdata/usb.ids", tools.make_jobs())
            tools.run("make {shared[install-shared,install-static]} PREFIX=/jolt-prefix DESTDIR={}", self.installdir)

        with tools.cwd(self.installdir, "jolt-prefix"):
            for pc in tools.glob("lib/pkgconfig/*.pc"):
                tools.replace_in_file(pc, "/jolt-prefix", "${{pcfiledir}}/../..")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir, "jolt-prefix"):
            artifact.collect("*", symlinks=True)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(LibudevZero)
