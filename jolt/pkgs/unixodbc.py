from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry


@attributes.requires("requires_src")
@autotools.requires()
@cxxinfo.publish(libraries=["odbc"])
@attributes.requires("requires_compiler")
class UnixODBC(autotools.Autotools):
    name = "unixodbc"
    version = Parameter("2.3.14", help="unixODBC version.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://github.com/lurcher/unixODBC/releases/download/v{version}/unixODBC-{version}.tar.gz"]
    srcdir = "{fetch[src]}/unixODBC-{version}"
    options = [
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(UnixODBC)
