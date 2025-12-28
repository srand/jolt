from jolt import Parameter, attributes
from jolt.plugins import autotools, fetch, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@pkgconfig.cxxinfo(["readline"])
class Readline(autotools.Autotools):
    name = "readline"
    version = Parameter("8.2", help="Readline version.")
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/readline/readline-{version}.tar.gz"]
    srcdir = "{fetch[src]}/readline-{version}"


TaskRegistry.get().add_task_class(Readline)
