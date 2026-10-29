from jolt import attributes, Parameter
from jolt.plugins import autotools, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.options("options_{_variant}")
@attributes.requires("requires_compiler")
class Binutils(autotools.Autotools):
    """ GNU assembler, linker and binary tools """

    name = "binutils"
    version = Parameter("2.47", help="GNU Binutils version.")
    target = Parameter(required=False, help="Target of cross tools, such as arm-none-eabi. Native tools if not set.")
    requires_compiler = ["compiler/c"]
    requires_src = ["fetch:alias=src,url=https://ftpmirror.gnu.org/gnu/binutils/binutils-{version}.tar.xz"]
    srcdir = "{fetch[src]}/binutils-{version}"
    options = [
        "--disable-nls",
        "--disable-werror",
        "--enable-plugins",
        "--with-system-zlib=no",
        # Documentation requires makeinfo
        "MAKEINFO=true",
    ]
    options_cross = ["--target={target}"]
    """ Options passed to the ``configure`` script for cross tools. """
    options_native = []
    """ Options passed to the ``configure`` script for native tools. """

    @property
    def _variant(self):
        return "cross" if self.target.is_set() else "native"


TaskRegistry.get().add_task_class(Binutils)
