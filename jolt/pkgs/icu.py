from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["icuio", "icui18n", "icuuc", "icudata"])
@attributes.requires("requires_compiler")
class Icu(autotools.Autotools):
    """ International Components for Unicode, the ICU4C libraries and their data """

    name = "icu"
    version = Parameter("79.1", help="ICU version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://github.com/unicode-org/icu/releases/download/release-{version}/icu4c-{version}-sources.tgz"]
    srcdir = "{fetch[src]}/icu/source"
    options = [
        "--disable-samples",
        "--disable-tests",
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
        "{pic[CFLAGS=-fPIC CXXFLAGS=-fPIC,]}",
    ]

    def run(self, deps, tools):
        super().run(deps, tools)
        # The prefix in icu-config must follow the artifact when it is relocated
        with tools.cwd(tools.autotools().installdir, "jolt-prefix", "bin"):
            tools.replace_in_file("icu-config", 'default_prefix="/jolt-prefix"', 'default_prefix="$(cd "$(dirname "$0")/.." && pwd)"')

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")
        else:
            artifact.cxxinfo.macros.append("U_STATIC_IMPLEMENTATION")


TaskRegistry.get().add_task_class(Icu)
