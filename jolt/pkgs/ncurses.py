from jolt import BooleanParameter, Parameter, attributes
from jolt.plugins import autotools, fetch, pkgconfig
from jolt.tasks import TaskRegistry
import os


@attributes.requires("requires_src")
@autotools.requires()
@pkgconfig.requires()
class Ncurses(autotools.Autotools):
    name = "ncurses"
    version = Parameter("6.6", help="Ncurses version.")
    widechar = BooleanParameter(False, help="Build ncurses with wide character support.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_src = ["fetch:alias=src,url=https://invisible-mirror.net/archives/ncurses/ncurses-{version}.tar.gz"]
    srcdir = "{fetch[src]}/ncurses-{version}"
    options = [
        "--{widechar[enable,disable]}-widec",
        "--{shared[with,without]}-shared",
        "--enable-pc-files",
        "--with-pkg-config-libdir=/jolt-prefix/lib/pkgconfig",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Ncurses)
