from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, protobuf
from jolt.plugins import cmake, cxxinfo, git, python
from jolt.tasks import TaskRegistry


@python.requires()
@attributes.requires("requires_compiler")
class NanopbPython(python.PythonEnv):
    """ Python environment for the nanopb generator """

    name = "nanopb/python"
    requires_compiler = ["virtual/compiler/c"]
    # The Python runtime must not be older than protoc, which generates the
    # Python code of the generator's own options. Protobuf 36.x pairs with 7.36.x.
    requirements = ["protobuf==7.36.2"]


@attributes.requires("requires_git")
@attributes.requires("requires_generator")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["protobuf-nanopb"])
@attributes.requires("requires_compiler")
class Nanopb(cmake.CMake):
    """ Protocol Buffers for embedded systems: the runtime library and the generator """

    name = "nanopb"
    version = Parameter("0.4.9.2", help="nanopb version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c"]
    # The generator runs protoc and needs the protobuf Python package
    requires_generator = ["nanopb/python", "protobuf"]
    requires_git = ["git:url=https://github.com/nanopb/nanopb.git,rev=nanopb-{version}"]
    srcdir = "{git[nanopb]}"
    # The generator is installed in the artifact instead of the site
    # packages of the Python that runs the build
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_STATIC_LIBS={shared[OFF,ON]}",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
        "nanopb_PYTHON_INSTDIR_OVERRIDE:STRING=lib/python",
    ]

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.cxxinfo.incpaths.append("include/nanopb")
        artifact.environ.PATH.append("bin")
        artifact.environ.PYTHONPATH.append("lib/python")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(Nanopb)
TaskRegistry.get().add_task_class(NanopbPython)
