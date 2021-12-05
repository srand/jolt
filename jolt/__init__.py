from .tasks import Alias
from .tasks import Download
from .tasks import Script
from .tasks import Task
from .tasks import TaskGenerator
from .tasks import Test
from .tasks import Resource
from .tasks import Export
from .tasks import Parameter
from .tasks import BooleanParameter
from .tasks import ListParameter
from .tasks import attributes
from .cache import Artifact
from .cache import Context
from .tools import Tools
from .version import __version__
from . import expires
from . import influence

__all__ = (
    "Alias",
    "Download",
    "Script",
    "Task",
    "TaskGenerator",
    "Test",
    "Resource",
    "Export",
    "Parameter",
    "BooleanParameter",
    "ListParameter",
    "attributes",
    "Artifact",
    "Context",
    "Tools",
    "__version__",
    "expires",
    "influence",
)

name = "jolt"


def include(joltfile):
    """ Include another Python file """
    try:
        from os import path
        from sys import _getframe
        from jolt.loader import JoltLoader
        filepath = _getframe().f_back.f_code.co_filename
        filepath = path.dirname(filepath)
        filepath = path.join(filepath, joltfile)
        JoltLoader.get()._load_file(filepath)
    except Exception as e:
        from jolt.error import raise_error
        raise_error("failed to load '{0}': {1}", joltfile, str(e))
