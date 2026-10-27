from jolt import attributes, Parameter
from jolt.pkgs import m4
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_m4")
@attributes.requires("requires_src")
class Bison(autotools.Autotools):
    """ GNU parser generator """

    name = "bison"
    version = Parameter("3.8.2", help="GNU Bison version.")
    requires_m4 = ["m4"]
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/bison/bison-{version}.tar.xz"]
    srcdir = "{fetch[src]}/bison-{version}"
    options = [
        "--enable-relocatable",
        "M4=m4",
    ]
    """ Options passed to the ``configure`` script. Bison finds its data files relative to its executable, and m4 in ``PATH``. """


TaskRegistry.get().add_task_class(Bison)
