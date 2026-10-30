from jolt import attributes, Parameter
from jolt.pkgs import cmake, compiler
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(incpaths=["include/eigen3"])
@attributes.requires("requires_compiler")
class Eigen(cmake.CMake):
    """ C++ template library for linear algebra """

    name = "eigen"
    version = Parameter("5.0.1", help="Eigen version.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:url=https://gitlab.com/libeigen/eigen.git,rev={version}"]
    srcdir = "{git[eigen]}"
    options = [
        "BUILD_TESTING=OFF",
        # BLAS and LAPACK need a Fortran compiler
        "EIGEN_BUILD_BLAS=OFF",
        "EIGEN_BUILD_DEMOS=OFF",
        "EIGEN_BUILD_DOC=OFF",
        "EIGEN_BUILD_LAPACK=OFF",
        "EIGEN_BUILD_PKGCONFIG=ON",
        "EIGEN_BUILD_TESTING=OFF",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.CMAKE_PREFIX_PATH.append(".")


TaskRegistry.get().add_task_class(Eigen)
