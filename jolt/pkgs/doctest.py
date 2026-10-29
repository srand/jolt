from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish()
@attributes.requires("requires_compiler")
class Doctest(cmake.CMake):
    """ C++ testing framework """

    name = "doctest"
    version = Parameter("2.5.3", help="doctest version.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://github.com/doctest/doctest.git,rev=v{version}"]
    srcdir = "{git[doctest]}"
    options = [
        "DOCTEST_WITH_MAIN_IN_STATIC_LIB=OFF",
        "DOCTEST_WITH_TESTS=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Doctest)
