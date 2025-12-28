from jolt.plugins import python
from jolt.tasks import TaskRegistry


class Python(python.PythonEnv):
    """ Builds and publishes a Python virtual environment with specified packages. """

    name = "python"
    requirements = [
        "setuptools",
        "mako",
        "meson",
        "pyyaml",
    ]


TaskRegistry.get().add_task_class(Python)
