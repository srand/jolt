from jolt import BooleanParameter, Parameter, attributes
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.requires()
class Ncurses(autotools.Autotools):
    name = "ncurses"
    version = Parameter("6.6", help="Ncurses version.")
    widechar = BooleanParameter(False, help="Build ncurses with wide character support.")
    requires_src = ["fetch:alias=src,url=https://invisible-mirror.net/archives/ncurses/ncurses-{version}.tar.gz"]
    srcdir = "{fetch[src]}/ncurses-{version}"
    options = ["--{widechar[enable,disable]}-widec"]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        artifact.cxxinfo.libraries.append("ncurses{widechar[w,]}")

        with tools.tmpdir() as tmp, tools.cwd(tmp):
            tools.write_file(
                "ncurses.pc",
                """
prefix=${{pcfiledir}}/../..
exec_prefix=${{prefix}}
libdir=${{prefix}}/lib
includedir=${{prefix}}/include

Name: ncurses
Description: ncurses library
Version: {version}
URL: https://invisible-island.net/ncurses
Libs:  -lncurses{widechar[w,]}
Libs.private:  -ldl 
Cflags:  -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=600
""")
            artifact.collect("ncurses.pc", "lib/pkgconfig/ncurses.pc")
            


TaskRegistry.get().add_task_class(Ncurses)
