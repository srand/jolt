from .error import JoltError
from .error import JoltCommandError
from .error import JoltTimeoutError

from .tasks import Alias
from .tasks import BooleanParameter
from .tasks import Chroot
from .tasks import Download
from .tasks import EnvironExport
from .tasks import Export
from .tasks import IntParameter
from .tasks import ListParameter
from .tasks import MultiTask
from .tasks import Parameter
from .tasks import Resource
from .tasks import Runner
from .tasks import Script
from .tasks import Task
from .tasks import TaskGenerator
from .tasks import Test
from .tasks import attributes

from .cache import Artifact
from .cache import Context

from .tools import Tools

from .version import __version__
from . import expires
from . import influence

__all__ = (
    "Alias",
    "Artifact",
    "BooleanParameter",
    "Chroot",
    "Context",
    "Download",
    "EnvironExport",
    "Export",
    "IntParameter",
    "JoltError",
    "JoltCommandError",
    "JoltTimeoutError",
    "ListParameter",
    "MultiTask",
    "Parameter",
    "Resource",
    "Runner",
    "Script",
    "Task",
    "TaskGenerator",
    "Test",
    "Tools",
    "__version__",
    "attributes",
    "expires",
    "influence",
)

name = "jolt"


def include(joltfile, joltdir=None):
    """ Include another Python file with Jolt tasks.

      :param joltfile: The path to the Jolt file to include.
      :type joltfile: str

      :param joltdir: The directory to search for Jolt files.
      :type joltdir: str

    Example:

      .. code-block:: python

            from jolt import include

            include("joltfile.py")

      """
    try:
        from os import path
        from jolt.loader import JoltLoader
        import sys
        caller_dir = path.dirname(sys._getframe().f_back.f_code.co_filename)
        if joltdir is not None:
            joltdir = path.join(caller_dir, joltdir)
        else:
            joltdir = caller_dir
        filepath = path.join(caller_dir, joltfile)
        JoltLoader.get().load_file(filepath, joltdir=joltdir)
    except Exception as e:
        from jolt.error import raise_error
        raise_error("Failed to load '{0}': {1}", joltfile, str(e))
