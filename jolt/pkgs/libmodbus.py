from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import autotools, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@autotools.requires()
@cxxinfo.publish(libraries=["modbus"])
@attributes.requires("requires_compiler")
class Libmodbus(autotools.Autotools):
    """ Modbus library for RTU (serial) and TCP """

    name = "libmodbus"
    version = Parameter("3.2.0", help="libmodbus version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:clean=true,url=https://github.com/stephane/libmodbus.git,rev=v{version}"]
    srcdir = "{git[libmodbus]}"
    options = [
        "--disable-tests",
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
        "{_pic_option}",
    ]

    @property
    def _pic_option(self):
        # Shared libraries are always position independent
        if self.shared:
            return ""
        return "--with-pic" if self.pic else "--without-pic"

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include/modbus")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libmodbus)
