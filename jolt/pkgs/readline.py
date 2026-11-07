from jolt import Alias, Parameter, attributes
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


class VirtualReadline(Alias):
    """
    The line editing library that packages use.

    Selects GNU Readline. libedit is a BSD-licensed alternative for projects
    that support its emulation of the Readline API, ``editline/readline.h``.
    """

    name = "virtual/readline"
    requires = ["readline"]


TaskRegistry.get().add_task_class(Readline)
TaskRegistry.get().add_task_class(VirtualReadline)
