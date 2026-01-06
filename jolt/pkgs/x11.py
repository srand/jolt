from jolt import Alias
from jolt.tasks import TaskRegistry


class GlProto(Alias):
    name = "glproto"
    requires = ["xorg/glproto"]


class Libx11(Alias):
    name = "libx11"
    requires = ["xorg/libx11"]


class Libxext(Alias):
    name = "libxext"
    requires = ["xorg/libxext"]


class Libxshmfence(Alias):
    name = "libxshmfence"
    requires = ["xorg/libxshmfence"]


class LibXcb(Alias):
    name = "libxcb"
    requires = ["xorg/libxcb"]


class LibX11Xcb(Alias):
    name = "libx11-xcb"
    requires = ["xorg/libx11-xcb"]


class Xproto(Alias):
    name = "xproto"
    requires = ["xorg/xproto"]


class LibXrandr(Alias):
    name = "libxrandr"
    requires = ["xorg/libxrandr"]


TaskRegistry.get().add_task_class(GlProto)
TaskRegistry.get().add_task_class(Libx11)
TaskRegistry.get().add_task_class(LibX11Xcb)
TaskRegistry.get().add_task_class(LibXcb)
TaskRegistry.get().add_task_class(Libxext)
TaskRegistry.get().add_task_class(LibXrandr)
TaskRegistry.get().add_task_class(Libxshmfence)
TaskRegistry.get().add_task_class(Xproto)
