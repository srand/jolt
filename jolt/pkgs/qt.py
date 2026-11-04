from jolt import attributes, Parameter, BooleanParameter
from jolt.pkgs import cmake, compiler, dbus, libglvnd, ninja, protobuf, x11
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_dbus_{system}")
@attributes.requires("requires_git")
@attributes.requires("requires_{system}_gl_{gl}")
@attributes.requires("requires_ninja")
@attributes.requires("requires_protobuf")
@attributes.system
@cmake.options("options_{system}_gl_{gl}")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class Qt(cmake.CMake):
    name = "qt"
    version = Parameter("6.12.0", help="Qt version.")
    gl = BooleanParameter(True, help="Enable OpenGL support.")
    webengine = BooleanParameter(False, help="Enable WebEngine module.")

    generator = "Ninja"
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_dbus_linux = ["dbus"]
    requires_git = ["git:path={buildroot}/git-qt,url=https://github.com/qt/qt5.git,rev=v{version},submodules=true"]
    requires_ninja = ["ninja"]
    requires_linux_gl_true = ["libglvnd", "libx11"]
    """ Libraries for OpenGL on Linux. GLX is used through Xlib. """
    requires_protobuf = ["protobuf"]
    srcdir = "{git[qt5]}"

    options = [
        # Qt OPC UA accesses ASN1_TIME directly, which is opaque in OpenSSL 4
        "BUILD_qtopcua=OFF",
        "BUILD_qtwebengine={webengine[ON,OFF]}",
    ]

    def run(self, deps, tools):
        if self.system != "linux" or not self.gl:
            return super().run(deps, tools)
        # CMake's X11::X11 target only has the include directory of X11/X.h,
        # which is in the protocol headers, not that of Xlib.h in libX11
        cflags = tools.run("pkg-config --cflags x11").strip()
        with tools.environ(
            CFLAGS=cflags + " " + tools.getenv("CFLAGS", ""),
            CXXFLAGS=cflags + " " + tools.getenv("CXXFLAGS", ""),
        ):
            super().run(deps, tools)


TaskRegistry.get().add_task_class(Qt)
