from jolt import attributes, Parameter
from jolt.pkgs import compiler, libffi, meson, pcre2, zlib
from jolt.plugins import git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libffi")
@attributes.requires("requires_pcre2")
@attributes.requires("requires_zlib")
@meson.requires()
@attributes.requires("requires_compiler")
class GLib(meson.Meson):
    name = "glib"
    version = Parameter("2.90.1", help="GLib version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://gitlab.gnome.org/GNOME/glib.git,rev={version},submodules=true"]
    requires_libffi = ["libffi"]
    requires_pcre2 = ["pcre2:pic=true"]
    requires_zlib = ["zlib:pic=true"]
    srcdir = "{git[glib]}"
    options = [
        "documentation=false",
        "introspection=disabled",
        "man-pages=disabled",
        "tests=false",
        # Dependencies that would come from the host
        "libelf=disabled",
        "libmount=disabled",
        "selinux=disabled",
        "sysprof=disabled",
        # Use the requirements instead of the copies of dependencies in subprojects
        "wrap_mode=nofallback",
    ]
    """ Options passed to ``meson setup``. """

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(GLib)
