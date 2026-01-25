from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import ncurses
from jolt.plugins import cxxinfo, git, autotools, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_ncurses")
@autotools.requires()
@pkgconfig.requires()
@cxxinfo.publish(libraries=["edit"])
class Libedit(autotools.Autotools):
    name = "libedit"
    version = Parameter("20251016-3.1", help="Libedit version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_git = ["fetch:alias=src,url=https://thrysoee.dk/editline/libedit-{version}.tar.gz"]
    requires_ncurses = ["ncurses=ncurses:shared=true"]  # No pkgconfig module without shared libs
    srcdir = "{fetch[src]}/libedit-{version}"
    options = [
        "--disable-examples",
        "--{shared[with,without]}-shared",
        "--enable-pc-files",
        "--with-pkg-config-libdir=/jolt-prefix/lib/pkgconfig",
    ]

    def run(self, deps, tools):
        with tools.environ(
            CFLAGS=tools.run("pkg-config --cflags ncurses").strip() + " " + tools.getenv("CFLAGS", ""),
            LDFLAGS=tools.run("pkg-config --libs ncurses").strip() + " " + tools.getenv("LDFLAGS", ""),
        ):
            super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libedit)
