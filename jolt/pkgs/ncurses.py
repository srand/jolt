from jolt import BooleanParameter, Parameter, attributes
from jolt.plugins import autotools, fetch, pkgconfig
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler
import os


@attributes.requires("requires_src")
@autotools.requires()
@pkgconfig.requires()
@attributes.requires("requires_compiler")
class Ncurses(autotools.Autotools):
    name = "ncurses"
    version = Parameter("6.6", help="ncurses version.")
    widechar = BooleanParameter(False, help="Build ncurses with wide character support.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://invisible-mirror.net/archives/ncurses/ncurses-{version}.tar.gz"]
    srcdir = "{fetch[src]}/ncurses-{version}"
    options = [
        "--{widechar[enable,disable]}-widec",
        "--{shared[with,without]}-shared",
        "--enable-pc-files",
        "--with-pkg-config-libdir=/jolt-prefix/lib/pkgconfig",
    ]

    def run(self, deps, tools):
        if not self.pic:
            return super().run(deps, tools)
        # configure has no option for it, and only uses its default -O2 without CFLAGS
        with tools.environ(CFLAGS=tools.getenv("CFLAGS", "-O2") + " -fPIC"):
            super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Ncurses)
