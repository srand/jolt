from jolt import attributes, Parameter, BooleanParameter
from jolt.pkgs import cmake, dbus, ninja, libglvnd
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_cmake")
@attributes.requires("requires_dbus")
@attributes.requires("requires_git")
@attributes.requires("requires_ninja")
@attributes.requires("requires_{system}")
@attributes.requires("requires_gl_{gl}")
@attributes.system
@attributes.attribute("options", "options_gl_{gl}")
class Qt(cmake.CMake):
    name = "qt"
    version = Parameter("6.10.1", help="Qt version.")
    gl = BooleanParameter(True, help="Enable OpenGL support.")

    generator = "Ninja"
    requires_cmake = ["cmake"]
    requires_dbus = ["dbus"]
    requires_git = ["git:url=https://github.com/qt/qt5.git,path=build/git-qt,rev=v{version},submodules=true"]
    requires_ninja = ["ninja"]
    requires_gl_true = ["libglvnd"]

    options_gl_true = [
        "CMAKE_PREFIX_PATH={deps[libglvnd].path}",
        "CMAKE_INSTALL_RPATH={deps[libglvnd].path}/lib",
        "CMAKE_LIBRARY_PATH={deps[libglvnd].path}/lib",
        "CMAKE_INCLUDE_PATH={deps[libglvnd].path}/include",
        "OPENGL_gl_LIBRARY={deps[libglvnd].path}/lib/libGL.so",
        "OPENGL_INCLUDE_DIR={deps[libglvnd].path}/include",
        "OPENGL_glx_LIBRARY={deps[libglvnd].path}/lib/libGLX.so",
        "OPENGL_glx_INCLUDE_DIR={deps[libglvnd].path}/include",
    ]

    def run(self, deps, tools):
        self.deps = deps
        with tools.cwd("{git[qt5]}"):
            super().run(deps, tools)


TaskRegistry.get().add_task_class(Qt)
