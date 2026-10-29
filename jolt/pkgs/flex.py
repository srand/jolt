from jolt import attributes, Parameter
from jolt.pkgs import m4
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_m4")
@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["fl"])
@attributes.requires("requires_compiler")
class Flex(autotools.Autotools):
    """ Fast lexical analyzer generator """

    name = "flex"
    version = Parameter("2.6.4", help="flex version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_m4 = ["m4"]
    requires_src = ["fetch:alias=src,url=https://github.com/westes/flex/releases/download/v{version}/flex-{version}.tar.gz"]
    srcdir = "{fetch[src]}/flex-{version}"
    options = ["M4=m4"]
    """ Options passed to the ``configure`` script. Flex finds m4 in ``PATH``. """


TaskRegistry.get().add_task_class(Flex)
