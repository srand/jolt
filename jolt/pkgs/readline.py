from jolt import Parameter, attributes
from jolt.plugins import autotools, fetch, pkgconfig
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler


@attributes.requires("requires_src")
@pkgconfig.to_cxxinfo(["readline"])
@attributes.requires("requires_compiler")
class Readline(autotools.Autotools):
    name = "readline"
    version = Parameter("8.3", help="GNU Readline version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/readline/readline-{version}.tar.gz"]
    srcdir = "{fetch[src]}/readline-{version}"


TaskRegistry.get().add_task_class(Readline)
