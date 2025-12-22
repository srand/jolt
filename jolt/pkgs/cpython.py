from jolt import attributes, Parameter
from jolt.plugins import autotools, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
class CPython(autotools.Autotools):
    """ Builds and publishes CPython libraries and headers. """

    name = "cpython"
    version = Parameter("3.14.2", help="CPython version.")
    requires_git = ["git:url=https://github.com/python/cpython.git,rev=v{version}"]
    srcdir = "{git[cpython]}"


TaskRegistry.get().add_task_class(CPython)
