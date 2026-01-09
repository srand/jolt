from jolt import attributes, Parameter, Task
from jolt.plugins import fetch, autotools, libtool, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires()
class XorgMacros(autotools.Autotools):
    name = "xorg/macros"
    version = Parameter("1.20.2", help="Xorg Macros version.")

    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/util/macros.git,rev=util-macros-{version}"]
    srcdir = "{git[macros]}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Inputproto(autotools.Autotools):
    name = "xorg/inputproto"
    version = Parameter("2.3.2", help="Inputproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/inputproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/inputproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Glproto(autotools.Autotools):
    name = "xorg/glproto"
    version = Parameter("1.4.17", help="Glproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/glproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/glproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Kbproto(autotools.Autotools):
    name = "xorg/kbproto"
    version = Parameter("1.0.7", help="Kbproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/kbproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/kbproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Randrproto(autotools.Autotools):
    name = "xorg/randrproto"
    version = Parameter("1.5.0", help="Randrproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/randrproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/randrproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Renderproto(autotools.Autotools):
    name = "xorg/renderproto"
    version = Parameter("0.11.1", help="Renderproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/renderproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/renderproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@attributes.requires("requires_xcb")
@autotools.requires()
@pkgconfig.requires()
class XcbKeysyms(autotools.Autotools):
    name = "xorg/xcb-keysyms"
    version = Parameter("0.4.1", help="XCB Keysyms version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/xcb-util-keysyms-{version}.tar.xz"]
    requires_xcb = ["xorg/libxcb"]
    srcdir = "{fetch[src]}/xcb-util-keysyms-{version}"


@attributes.requires("requires_git")
@attributes.requires("requires_xorg_macros")
@autotools.requires()
@pkgconfig.requires()
class XcbProto(autotools.Autotools):
    name = "xorg/xcb-proto"
    version = Parameter("1.17.0", help="Libxcb_proto version.")
    requires_git = ["git:url=https://gitlab.freedesktop.org/xorg/proto/xcbproto.git,rev=xcb-proto-{version}"]
    requires_xorg_macros = ["xorg/macros"]
    srcdir = "{git[xcbproto]}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@attributes.requires("requires_xproto")
@autotools.requires()
@libtool.relocate()
@pkgconfig.requires()
class Xau(autotools.Autotools):
    name = "xorg/libxau"
    version = Parameter("1.0.12", help="Xau version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXau-{version}.tar.gz"]
    requires_xproto = ["xorg/xproto"]
    srcdir = "{fetch[src]}/libXau-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@attributes.requires("requires_xproto")
@autotools.requires()
@libtool.relocate()
@pkgconfig.requires()
class LibXdmcp(autotools.Autotools):
    name = "xorg/libxdmcp"
    version = Parameter("1.1.5", help="LibXdmcp version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXdmcp-{version}.tar.gz"]
    requires_xproto = ["xorg/xproto"]
    srcdir = "{fetch[src]}/libXdmcp-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@attributes.requires("requires_x11")
@attributes.requires("requires_xextproto")
@attributes.requires("requires_xproto")
@autotools.requires()
@pkgconfig.requires()
class Xext(autotools.Autotools):
    name = "xorg/libxext"
    version = Parameter("1.3.6", help="Xext version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXext-{version}.tar.gz"]
    requires_x11 = ["xorg/libx11"]
    requires_xextproto = ["xorg/xextproto"]
    requires_xproto = ["xorg/xproto"]
    srcdir = "{fetch[src]}/libXext-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Xextproto(autotools.Autotools):
    name = "xorg/xextproto"
    version = Parameter("7.3.0", help="Xextproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/xextproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/xextproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Xproto(autotools.Autotools):
    name = "xorg/xproto"
    version = Parameter("7.0.31", help="Xproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/xproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/xproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Xf86vidmodeproto(autotools.Autotools):
    name = "xorg/xf86vidmodeproto"
    version = Parameter("2.3.1", help="Xf86vidmodeproto version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/proto/xf86vidmodeproto-{version}.tar.gz"]
    srcdir = "{fetch[src]}/xf86vidmodeproto-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_src")
@autotools.requires()
class Xtrans(autotools.Autotools):
    name = "xorg/xtrans"
    version = Parameter("1.6.0", help="Xtrans version.")
    requires_macros = ["xorg/macros"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/xtrans-{version}.tar.gz"]
    srcdir = "{fetch[src]}/xtrans-{version}"


@attributes.requires("requires_randrproto")
@attributes.requires("requires_src")
@attributes.requires("requires_xext")
@attributes.requires("requires_xrender")
@autotools.requires()
@libtool.relocate()
class Xrandr(autotools.Autotools):
    name = "xorg/libxrandr"
    version = Parameter("1.5.4", help="Xrandr version.")
    requires_randrproto = ["xorg/randrproto"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXrandr-{version}.tar.gz"]
    requires_xext = ["xorg/libxext"]
    requires_xrender = ["xorg/libxrender"]
    srcdir = "{fetch[src]}/libXrandr-{version}"


@attributes.requires("requires_macros")
@attributes.requires("requires_renderproto")
@attributes.requires("requires_src")
@attributes.requires("requires_x11")
@autotools.requires()
@libtool.relocate()
@pkgconfig.requires()
class Xrender(autotools.Autotools):
    name = "xorg/libxrender"
    version = Parameter("0.9.12", help="Xrender version.")
    requiers_macros = ["xorg/macros"]
    requires_renderproto = ["xorg/renderproto"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXrender-{version}.tar.gz"]
    requires_x11 = ["xorg/libx11"]
    srcdir = "{fetch[src]}/libXrender-{version}"


@attributes.requires("requires_git")
@attributes.requires("requires_xproto")
@attributes.requires("requires_xorg_macros")
@pkgconfig.to_cxxinfo(["xshmfence"])
@pkgconfig.requires()
@autotools.requires()
@libtool.relocate()
@libtool.relocate()
class Libxshmfence(autotools.Autotools):
    name = "xorg/libxshmfence"
    version = Parameter("1.3.3", help="Libxshmfence version.")

    requires_git = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libxshmfence-{version}.tar.gz"]
    requires_xproto = ["xproto"]
    requires_xorg_macros = ["xorg/macros"]
    srcdir = "{fetch[src]}/libxshmfence-{version}"


@attributes.common_metadata()
@attributes.requires("requires_libx11")
@attributes.requires("requires_src")
@attributes.requires("requires_xext")
@attributes.requires("requires_xextproto")
@attributes.requires("requires_xf86vidmodeproto")
@attributes.requires("requires_xorg_macros")
@attributes.requires("requires_xproto")
@autotools.requires()
@pkgconfig.requires()
@libtool.relocate()
class Libxxf86vm(autotools.Autotools):
    name = "xorg/libxxf86vm"
    version = "1.1.6"
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libXxf86vm-{version}.tar.gz"]
    srcdir = "{fetch[src]}/libXxf86vm-{version}"
    requires_libx11 = ["xorg/libx11"]
    requires_xext = ["xorg/libxext"]
    requires_xextproto = ["xorg/xextproto"]
    requires_xf86vidmodeproto = ["xorg/xf86vidmodeproto"]
    requires_xorg_macros = ["xorg/macros"]
    requires_xproto = ["xorg/xproto"]


@attributes.requires("requires_git")
@attributes.requires("requires_xau")
@attributes.requires("requires_xorg_macros")
@attributes.requires("requires_xcb_proto")
@pkgconfig.to_cxxinfo(["xcb"])
@autotools.requires()
@libtool.relocate()
class Libxcb(autotools.Autotools):
    name = "xorg/libxcb"
    version = Parameter("1.17.0", help="Libxcb version.")

    requires_git = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libxcb-{version}.tar.gz"]
    requires_xau = ["xorg/libxau"]
    requires_xorg_macros = ["xorg/macros"]
    requires_xcb_proto = ["xorg/xcb-proto"]
    srcdir = "{fetch[src]}/libxcb-{version}"


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
@pkgconfig.to_cxxinfo(["x11", "x11-xcb"])
@libtool.relocate()
class Libx11(autotools.Autotools):
    name = "xorg/libx11"
    version = Parameter("1.8.12", help="Libx11 version.")

    requires_inputproto = ["xorg/inputproto"]
    requires_kbproto = ["xorg/kbproto"]
    requires_libxau = ["xorg/libxau"]
    requires_libxcb = ["xorg/libxcb"]
    requires_libxdmcp = ["xorg/libxdmcp"]
    requires_src = ["fetch:alias=src,url=https://www.x.org/releases/individual/lib/libX11-{version}.tar.gz"]
    requires_xextproto = ["xorg/xextproto"]
    requires_xorg_macros = ["xorg/macros"]
    requires_xproto = ["xorg/xproto"]
    requires_xtrans = ["xorg/xtrans"]
    srcdir = "{fetch[src]}/libX11-{version}"


@attributes.requires("requires_libx11")
@attributes.requires("requires_libxcb")
@attributes.common_metadata()
@libtool.relocate()
class LibX11Xcb(Task):
    """
    Republishes libx11 and libxcb as libx11-xcb for compatibility.

    Mainly, prefix must be shared in order to build mesa.
    """
    name = "xorg/libx11-xcb"
    requires_libx11 = ["xorg/libx11"]
    requires_libxcb = ["xorg/libxcb"]
    selfsustained = True

    def run(self, deps, tools):
        self.x11 = deps["xorg/libx11"]
        self.xcb = deps["xorg/libxcb"]

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
TaskRegistry.get().add_task_class(Libxcb)
TaskRegistry.get().add_task_class(LibXdmcp)
TaskRegistry.get().add_task_class(Libxxf86vm)
TaskRegistry.get().add_task_class(Randrproto)
TaskRegistry.get().add_task_class(Renderproto)
TaskRegistry.get().add_task_class(Xau)
TaskRegistry.get().add_task_class(XcbKeysyms)
TaskRegistry.get().add_task_class(XcbProto)
TaskRegistry.get().add_task_class(Xext)
TaskRegistry.get().add_task_class(Xextproto)
TaskRegistry.get().add_task_class(Xf86vidmodeproto)
TaskRegistry.get().add_task_class(XorgMacros)
TaskRegistry.get().add_task_class(Xproto)
TaskRegistry.get().add_task_class(Xrandr)
TaskRegistry.get().add_task_class(Xrender)
TaskRegistry.get().add_task_class(Xtrans)
TaskRegistry.get().add_task_class(Libxshmfence)
