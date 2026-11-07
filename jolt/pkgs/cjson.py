from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["cjson"])
@attributes.requires("requires_compiler")
class CJson(cmake.CMake):
    """ Ultralightweight JSON parser in ANSI C """

    name = "cjson"
    version = Parameter("1.7.19", help="cJSON version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/DaveGamble/cJSON.git,rev=v{version}"]
    srcdir = "{git[cJSON]}"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "ENABLE_CJSON_TEST=OFF",
        "ENABLE_CJSON_UNINSTALL=OFF",
        "ENABLE_CUSTOM_COMPILER_FLAGS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(CJson)
