from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, freetype, gperf, libexpat
from jolt.plugins import cxxinfo, git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_libs")
@meson.requires()
@cxxinfo.publish(libraries=["fontconfig"])
@attributes.requires("requires_compiler")
class Fontconfig(meson.Meson):
    """ Font configuration and customization library """

    name = "fontconfig"
    version = Parameter("2.18.3", help="Fontconfig version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://gitlab.freedesktop.org/fontconfig/fontconfig.git,rev={version}"]
    requires_libs = [
        "freetype:pic=true,shared={shared}",
        "gperf",
        "libexpat:pic=true,shared={shared}",
    ]
    """ Libraries and tools used by Fontconfig. """
    srcdir = "{git[fontconfig]}"
    options = [
        "cache-build=disabled",
        "default_library={shared[shared,static]}",
        "doc=disabled",
        "localstatedir=/var",
        "nls=disabled",
        "sysconfdir=/etc",
        "tests=disabled",
        "tools=disabled",
        "xml-backend=expat",
    ]
    """ Options passed to Meson, as ``option=value``. The configuration and font cache of the system are used at runtime. """


TaskRegistry.get().add_task_class(Fontconfig)
