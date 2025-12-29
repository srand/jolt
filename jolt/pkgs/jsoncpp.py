from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@pkgconfig.to_cxxinfo(["jsoncpp"])
@cmake.requires()
class JsonCPP(cmake.CMake):
    name = "jsoncpp"
    version = Parameter("1.9.6", help="JsonCPP version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_git = ["git:url=https://github.com/open-source-parsers/jsoncpp.git,rev={version}"]
    srcdir = "{git[jsoncpp]}"
    options = [
        "JSONCPP_WITH_TESTS={tests[ON,OFF]}",
    ]


TaskRegistry.get().add_task_class(JsonCPP)
