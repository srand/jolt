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

Customizing Packages
--------------------

A package can be customized by inheriting its task class in your recipe
and overriding attributes, such as the default version or the location
of the sources. The new class keeps the name of the package task and
replaces it, so other packages that require it use your version too:

.. code-block:: python

    from jolt import Parameter
    from jolt.pkgs import zlib

    class Zlib(zlib.Zlib):
        version = Parameter("1.3.1", help="Zlib version.")
        requires_git = ["git:url=https://git.example.com/mirrors/zlib.git,rev=v{version}"]

The source directory of a package refers to its repository by name, for
example ``{git[zlib]}``. If the repository is renamed in your URL,
override ``srcdir`` too. To add a variant alongside the original package
instead, give the new class a different ``name``.

Available Packages
------------------

.. jolt-packages::
