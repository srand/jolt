from jolt import attributes, Parameter, Task
from jolt.plugins import autotools, git, pkgconfig
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
class CPython(autotools.Autotools):
    """ Builds and publishes CPython libraries and headers. """

    name = "cpython"
    version = Parameter("3.14.2", help="CPython version.")
    requires_git = ["git:url=https://github.com/python/cpython.git,rev=v{version}"]
    srcdir = "{git[cpython]}"


@pkgconfig.cxxinfo("python3-embed")
@attributes.common_metadata()
class CPythonEmbed(Task):
    name = "cpython/embed"
    requires = ["cpython"]
    selfsustained = True

    def run(self, deps, tools):
        self.cpython = deps["cpython"]

    def publish(self, artifact, tools):
        with tools.cwd(self.cpython.path):
            artifact.collect("*", symlinks=True)


@pkgconfig.cxxinfo("python3")
@attributes.common_metadata()
class CPythonExtend(Task):
    name = "cpython/extend"
    requires = ["cpython"]
    selfsustained = True

    def run(self, deps, tools):
        self.cpython = deps["cpython"]

    def publish(self, artifact, tools):
        with tools.cwd(self.cpython.path):
            artifact.collect("*", symlinks=True)


TaskRegistry.get().add_task_class(CPython)
TaskRegistry.get().add_task_class(CPythonEmbed)
TaskRegistry.get().add_task_class(CPythonExtend)
