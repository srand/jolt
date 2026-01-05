from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.system
@cmake.requires()
@cmake.use_ninja()
class JsonCPP(cmake.CMake):
    name = "jsoncpp"
    version = Parameter("1.9.6", help="JsonCPP version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_git = ["git:url=https://github.com/open-source-parsers/jsoncpp.git,rev={version}"]
    srcdir = "{git[jsoncpp]}"
    options = [
        "JSONCPP_WITH_TESTS={tests[ON,OFF]}",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")
        artifact.cxxinfo.libpaths.append("lib")
        if self.system == "windows":
            artifact.cxxinfo.libraries.append("jsoncpp_static")
        else:
            artifact.cxxinfo.libraries.append("jsoncpp")


TaskRegistry.get().add_task_class(JsonCPP)
