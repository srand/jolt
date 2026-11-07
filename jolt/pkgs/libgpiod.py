from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import cxxinfo, git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@meson.requires()
@cxxinfo.publish(libraries=["gpiodcxx", "gpiod"])
@attributes.requires("requires_compiler")
class Libgpiod(meson.Meson):
    """ Library and tools for the GPIO character device of Linux """

    name = "libgpiod"
    version = Parameter("2.3.2", help="libgpiod version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    # GitHub mirror of git.kernel.org, maintained by the author
    requires_git = ["git:url=https://github.com/brgl/libgpiod.git,rev=v{version}"]
    srcdir = "{git[libgpiod]}"
    # Features that are enabled when found would use libraries of the build
    # host: libedit (interactive gpioset) and GLib (GObject bindings, D-Bus).
    options = [
        "bindings-cxx=enabled",
        "bindings-glib=disabled",
        "dbus=disabled",
        "default_library={shared[shared,static]}",
        "gpioset-interactive=disabled",
        "introspection=disabled",
        "systemd=disabled",
        "tests=disabled",
        "tools=enabled",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("bin")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libgpiod)
