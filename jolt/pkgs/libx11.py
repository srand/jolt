from jolt import attributes, Parameter, Task
from jolt.pkgs import xorg_macros, libxcb, libxcb_proto
from jolt.plugins import fetch, autotools, libtool, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.requires()
class Inputproto(autotools.Autotools):
    name = "inputproto"
    version = Parameter("2.3.2", help="Inputproto version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/inputproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/inputproto-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class Glproto(autotools.Autotools):
    name = "glproto"
    version = Parameter("1.4.17", help="Glproto version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/glproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/glproto-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class Kbproto(autotools.Autotools):
    name = "kbproto"
    version = Parameter("1.0.7", help="Kbproto version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/kbproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/kbproto-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class Xau(autotools.Autotools):
    name = "libxau"
    version = Parameter("1.0.12", help="Xau version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXau-{version}.tar.gz"]
    srcdir = "{fetch[src]}/libXau-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class LibXdmcp(autotools.Autotools):
    name = "libxdmcp"
    version = Parameter("1.1.5", help="LibXdmcp version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXdmcp-{version}.tar.gz"]
    srcdir = "{fetch[src]}/libXdmcp-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class Xext(autotools.Autotools):
    name = "libxext"
    version = Parameter("1.3.6", help="Xext version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXext-{version}.tar.gz"]
    srcdir = "{fetch[src]}/libXext-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class Xextproto(autotools.Autotools):
    name = "xextproto"
    version = Parameter("7.3.0", help="Xextproto version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/xextproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/xextproto-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class Xproto(autotools.Autotools):
    name = "xproto"
    version = Parameter("7.0.31", help="Xproto version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/xproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/xproto-{version}"


@attributes.requires("requires_src")
@autotools.requires()
class Xtrans(autotools.Autotools):
    name = "xtrans"
    version = Parameter("1.6.0", help="Xtrans version.")
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/xtrans-{version}.tar.gz"]
    srcdir = "{fetch[src]}/xtrans-{version}"


@attributes.requires("requires_inputproto")
@attributes.requires("requires_kbproto")
@attributes.requires("requires_libxau")
@attributes.requires("requires_libxcb")
@attributes.requires("requires_libxdmcp")
@attributes.requires("requires_src")
@attributes.requires("requires_xextproto")
@attributes.requires("requires_xorg_macros")
@attributes.requires("requires_xproto")
@attributes.requires("requires_xtrans")
@autotools.requires()
@pkgconfig.requires()
@pkgconfig.cxxinfo(["x11", "x11-xcb"])
@libtool.relocate()
class Libx11(autotools.Autotools):
    name = "libx11"
    version = Parameter("1.8.12", help="Libx11 version.")

    requires_inputproto = ["inputproto"]
    requires_kbproto = ["kbproto"]
    requires_libxau = ["libxau"]
    requires_libxcb = ["libxcb"]
    requires_libxdmcp = ["libxdmcp"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libX11-{version}.tar.gz"]
    requires_xextproto = ["xextproto"]
    requires_xorg_macros = ["xorg/macros"]
    requires_xproto = ["xproto"]
    requires_xtrans = ["xtrans"]
    srcdir = "{fetch[src]}/libX11-{version}"


@attributes.requires("requires_libx11")
@attributes.requires("requires_libxcb")
@attributes.common_metadata()
class LibX11Xcb(Task):
    """
    Republishes libx11 and libxcb as libx11-xcb for compatibility.

    Mainly, prefix must be shared in order to build mesa.
    """
    name = "libx11-xcb"
    requires_libx11 = ["libx11"]
    requires_libxcb = ["libxcb"]
    selfsustained = True

    def run(self, deps, tools):
        self.x11 = deps["libx11"]
        self.xcb = deps["libxcb"]

    def publish(self, artifact, tools):
        with tools.cwd(self.x11.path):
            artifact.collect("*", symlinks=True)
        with tools.cwd(self.xcb.path):
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(Glproto)
TaskRegistry.get().add_task_class(Inputproto)
TaskRegistry.get().add_task_class(Kbproto)
TaskRegistry.get().add_task_class(Libx11)
TaskRegistry.get().add_task_class(LibX11Xcb)
TaskRegistry.get().add_task_class(LibXdmcp)
TaskRegistry.get().add_task_class(Xau)
TaskRegistry.get().add_task_class(Xext)
TaskRegistry.get().add_task_class(Xextproto)
TaskRegistry.get().add_task_class(Xproto)
TaskRegistry.get().add_task_class(Xtrans)
