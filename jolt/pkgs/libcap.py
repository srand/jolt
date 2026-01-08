from jolt import attributes, Parameter, Task
from jolt.plugins import fetch
from jolt.tasks import TaskRegistry


@attributes.common_metadata()
@attributes.requires("requires_src")
class Libcap(Task):
    name = "libcap"
    version = Parameter("2.77", help="Libcap version.")
    requires_src = ["git:url=https://git.kernel.org/pub/scm/libs/libcap/libcap.git,rev=libcap-{version}"]
    srcdir = "{git[libcap]}"

    def run(self, deps, tools):
        self.installdir = tools.builddir("install")
        with tools.cwd(self.srcdir):
            tools.run("make -j {}", tools.cpu_count())
            tools.run("make install DESTDIR={}", self.installdir)

        # Patch pkgconfig files
        with tools.cwd(self.installdir):
            for pc in tools.glob("lib/pkgconfig/*.pc") + tools.glob("lib64/pkgconfig/*.pc"):
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
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(Libcap)
