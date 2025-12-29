from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
class Glslang(cmake.CMake):
    name = "glslang"
    version = Parameter("16.1.0", help="Glslang version.")
    requires_git = ["git:url=https://github.com/KhronosGroup/glslang.git,rev={version}"]

    def run(self, deps, tools):
        with tools.cwd("{git[glslang]}"):
            tools.run("./update_glslang_sources.py")
            super().run(deps, tools)


TaskRegistry.get().add_task_class(Glslang)
