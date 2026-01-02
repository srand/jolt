from jolt import Alias
from jolt.tasks import TaskRegistry
from jolt.pkgs import python


class Meson(Alias):
    """
    Alias for the Meson build system.

    Meson is included in the Python virtual environment task.
    """

    name = "meson"
    requires = ["python"]


TaskRegistry.get().add_task_class(Meson)
