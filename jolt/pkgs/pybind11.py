from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@attributes.requires("requires_compiler")
class Pybind11(cmake.CMake):
    """ Header-only library for exposing C++ to Python and Python to C++ """

    name = "pybind11"
    version = Parameter("3.1.0", help="pybind11 version.")
    requires_compiler = ["virtual/compiler/c"]
    requires_git = ["git:url=https://github.com/pybind/pybind11.git,rev=v{version}"]
    srcdir = "{git[pybind11]}"
    options = [
        "PYBIND11_TEST=OFF",
        # Consumers find Python themselves
        "PYBIND11_NOPYTHON=ON",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include")


TaskRegistry.get().add_task_class(Pybind11)
