from jolt import attributes, Parameter, Task
from jolt.plugins import cxxinfo, fetch
from jolt.tasks import BooleanParameter, TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["cap", "psx"])
class Libcap(Task):
    name = "libcap"
    version = Parameter("2.78", help="libcap version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_src = ["git:url=https://git.kernel.org/pub/scm/libs/libcap/libcap.git,rev=libcap-{version}"]
    srcdir = "{git[libcap]}"
    """ Source directory. """

    def run(self, deps, tools):
        self.installdir = tools.builddir("install")
        with tools.cwd(self.srcdir):
            tools.run("make {}", tools.make_jobs())
            tools.run("make install DESTDIR={}", self.installdir)

        # Patch pkgconfig files
        with tools.cwd(self.installdir):
            for pc in tools.glob("lib*/pkgconfig/*.pc"):
                tools.replace_in_file(
                    pc,
                    "prefix=/usr",
                    "prefix=${{pcfiledir}}/../..",
                )
                tools.replace_in_file(
                    pc,
                    "libdir=/",
                    "libdir=${{prefix}}/"
                )
                tools.replace_in_file(
                    pc,
                    "includedir=/",
                    "includedir=${{prefix}}/"
                )

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir):
            if self.shared:
                for lib in tools.glob("lib*/*.a"):
                    tools.unlink(lib)
            else:
                for lib in tools.glob("lib*/*.so*"):
                    tools.unlink(lib)
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(Libcap)
