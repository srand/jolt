from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import cxxinfo, git, meson
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@meson.requires()
@cxxinfo.publish(libraries=["lcms2"])
@attributes.requires("requires_compiler")
class Lcms2(meson.Meson):
    """ Little CMS color management engine """

    name = "lcms2"
    version = Parameter("2.20", help="Little CMS version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/mm2/Little-CMS.git,rev=lcms{version}"]
    srcdir = "{git[Little-CMS]}"
    # The image libraries are only used by the utilities
    options = [
        "default_library={shared[shared,static]}",
        "jpeg=disabled",
        "tests=disabled",
        "tiff=disabled",
        "utils=false",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")
            artifact.cxxinfo.macros.append("CMS_DLL")


TaskRegistry.get().add_task_class(Lcms2)
