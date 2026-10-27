Packages
========

Jolt includes recipes for building common third-party libraries and tools
from source, in the ``jolt.pkgs`` package. To use a package, import its
module in your recipe and require its task:

.. code-block:: python

    from jolt import Task
    from jolt.pkgs import zlib

    class App(Task):
        requires = ["zlib:shared=true"]

Parameters, such as ``version`` and ``shared``, are passed in the
requirement. Libraries publish compiler and linker information that the
C++ tasks of Jolt use automatically, as well as environment variables such
as ``PKG_CONFIG_PATH`` and ``CMAKE_PREFIX_PATH`` for other build systems.
Follow the links to the reference for the parameters of each task.

.. jolt-packages::
