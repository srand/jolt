from jolt import attributes, BooleanParameter, Parameter
from jolt.plugins import autotools, cxxinfo, fetch
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler


@attributes.requires("requires_src")
@cxxinfo.publish(libraries=["yaml"])
@attributes.requires("requires_compiler")
class Libyaml(autotools.Autotools):
    """ YAML parser and emitter in C """

    name = "libyaml"
    version = Parameter("0.2.5", help="LibYAML version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_src = ["fetch:alias=src,url=https://pyyaml.org/download/libyaml/yaml-{version}.tar.gz"]
    srcdir = "{fetch[src]}/yaml-{version}"
    options = [
        "--enable-shared={shared[yes,no]}",
        "--enable-static={shared[no,yes]}",
        "--{pic[with,without]}-pic",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Libyaml)
