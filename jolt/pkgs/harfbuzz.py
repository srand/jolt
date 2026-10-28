from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import freetype
from jolt.plugins import cxxinfo, git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_freetype")
@attributes.requires("requires_git")
@meson.requires()
@cxxinfo.publish(incpaths=["include/harfbuzz"], libraries=["harfbuzz"])
class Harfbuzz(meson.Meson):
    """ Text shaping engine """

    name = "harfbuzz"
    version = Parameter("15.0.0", help="HarfBuzz version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_freetype = ["freetype:pic=true,shared={shared}"]
    requires_git = ["git:url=https://github.com/harfbuzz/harfbuzz.git,rev={version}"]
    srcdir = "{git[harfbuzz]}"
    options = [
        "cairo=disabled",
        "chafa=disabled",
        "default_library={shared[shared,static]}",
        "docs=disabled",
        "freetype=enabled",
        "glib=disabled",
        "gobject=disabled",
        "icu=disabled",
        "introspection=disabled",
        "tests=disabled",
        "utilities=disabled",
    ]


TaskRegistry.get().add_task_class(Harfbuzz)
