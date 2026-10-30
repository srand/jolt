from jolt import attributes
from jolt.plugins import python
from jolt.tasks import TaskRegistry
from jolt.pkgs import compiler


@python.requires()
@attributes.requires("requires_compiler")
class Python(python.PythonEnv):
    """ Builds and publishes a Python virtual environment with specified packages. """

    name = "python"
    requires_compiler = ["virtual/compiler/c"]

    requirements = [
        "setuptools",
        "mako",
        "meson",
        "pyyaml",
    ]


TaskRegistry.get().add_task_class(Python)
