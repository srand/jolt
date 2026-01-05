from jolt import attributes, Parameter
from jolt.pkgs import cmake
from jolt.tasks import TaskRegistry
from jolt.plugins import git, cmake


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
class GoogleBenchmark(cmake.CMake):
    name = "google/benchmark"
    version = Parameter("1.9.4", help="Benchmark version.")
    requires_git = ["git:url=https://github.com/google/benchmark.git,rev=v{version},submodules=true"]
    options = ["BENCHMARK_ENABLE_TESTING=OFF"]
    srcdir = "{git[benchmark]}"


TaskRegistry.get().add_task_class(GoogleBenchmark)
