from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class SpirvTools(cmake.CMake):
    name = "spirv-tools"
    version = Parameter("2024.4", help="SPIRV-Tools version.")
    tests = BooleanParameter(False, help="Build tests.")
    requires_git = ["git:url=https://github.com/KhronosGroup/SPIRV-Tools.git,rev=v{version}"]
    srcdir = "{git[SPIRV-Tools]}"
    options = ["SPIRV_SKIP_TESTS={tests[OFF,ON]}"]

    def run(self, deps, tools):
        with tools.cwd(self.srcdir):
            tools.run("python3 utils/git-sync-deps")
        super().run(deps, tools)


TaskRegistry.get().add_task_class(SpirvTools)
