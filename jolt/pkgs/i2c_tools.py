from jolt import attributes, BooleanParameter, Parameter, Task
from jolt.pkgs import compiler
from jolt.plugins import cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["i2c"])
@attributes.requires("requires_compiler")
class I2cTools(Task):
    """ I2C/SMBus tools (i2cdetect, i2cget, i2cset, i2cdump, i2ctransfer) and libi2c """

    name = "i2c-tools"
    version = Parameter("4.4", help="i2c-tools version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://mirrors.edge.kernel.org/pub/software/utils/i2c-tools/i2c-tools-{version}.tar.xz"]
    srcdir = "{fetch[src]}/i2c-tools-{version}"
    """ Source directory. """

    @property
    def _make_args(self):
        # The tools link with the library that is built
        if self.shared:
            return "BUILD_DYNAMIC_LIB=1 BUILD_STATIC_LIB=0 USE_STATIC_LIB=0"
        return "BUILD_DYNAMIC_LIB=0 BUILD_STATIC_LIB=1 USE_STATIC_LIB=1"

    def run(self, deps, tools):
        self.installdir = tools.builddir("install", incremental=False)
        with tools.cwd(self.srcdir):
            tools.run("make clean")
            tools.run("make {} {_make_args} PREFIX=/jolt-prefix", tools.make_jobs())
            tools.run("make {_make_args} PREFIX=/jolt-prefix DESTDIR={installdir} install")

    def publish(self, artifact, tools):
        with tools.cwd(self.installdir, "jolt-prefix"):
            artifact.collect("*", symlinks=True)
        artifact.environ.PATH.append("bin")
        artifact.environ.PATH.append("sbin")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(I2cTools)
