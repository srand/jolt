from jolt import attributes, Parameter, BooleanParameter
from jolt.pkgs import cmake, dbus, ninja, libglvnd, protobuf
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
class Qt(cmake.CMake):
    name = "qt"
    version = Parameter("6.10.1", help="Qt version.")
    gl = BooleanParameter(True, help="Enable OpenGL support.")

    generator = "Ninja"
    requires_dbus_linux = ["dbus"]
    requires_git = ["git:path={buildroot}/git-qt,url=https://github.com/qt/qt5.git,rev=v{version},submodules=true"]
    requires_ninja = ["ninja"]
    requires_linux_gl_true = ["libglvnd"]
    requires_protobuf = ["protobuf"]
    srcdir = "{git[qt5]}"

    options_linux_gl_true = [
        "CMAKE_PREFIX_PATH={deps[libglvnd].path}",
        "CMAKE_INSTALL_RPATH={deps[libglvnd].path}/lib",
        "CMAKE_LIBRARY_PATH={deps[libglvnd].path}/lib",
        "CMAKE_INCLUDE_PATH={deps[libglvnd].path}/include",
        "OPENGL_gl_LIBRARY={deps[libglvnd].path}/lib/libGL.so",
        "OPENGL_INCLUDE_DIR={deps[libglvnd].path}/include",
        "OPENGL_glx_LIBRARY={deps[libglvnd].path}/lib/libGLX.so",
        "OPENGL_glx_INCLUDE_DIR={deps[libglvnd].path}/include",
    ]


TaskRegistry.get().add_task_class(Qt)
