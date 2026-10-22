Building C/C++
==============

Jolt provides task base classes for building C/C++ projects. The classes
are designed to be easily extended and customized to fit your specific
needs. They generate Ninja build files which are then used to build your
projects.


Basics
~~~~~~

Below is an example of a library and a program. The library contains a function
returning a message. The program calls this function and prints the message.

.. code-block:: c++

    // lib/message.cpp

    #include "message.h"

    const char *message() {
      return "Hello " RECIPIENT "!";
    }

.. code-block:: c++

    // program/main.cpp

    #include <cstdlib>
    #include <iostream>
    #include "lib/message.h"

    int main() {
      std::cout << message() << std::endl;
      return EXIT_SUCCESS;
    }


To build the library and the program we use this Jolt recipe:

.. code-block:: python

    from jolt import Parameter
    from jolt.plugins.ninja import CXXLibrary, CXXExecutable


    class Message(CXXLibrary):
        recipient = Parameter(default="world", help="Name of greeting recipient.")
        headers = ["lib/message.h"]
        sources = ["lib/message.cpp"]
        macros = ['RECIPIENT="{recipient}"']


    class HelloWorld(CXXExecutable):
        requires = ["message"]
        sources = ["program/main.cpp"]


Metadata
~~~~~~~~

Jolt automatically configures include paths, link libraries, and other build
attributes for the ``HelloWorld`` program based on metadata found in the artifact
of the ``Message`` library task. In the example, the ``Message`` library task relies
upon ``CXXLibrary.publish`` to collect public headers and to export the required
metadata such as include paths and linking information. Customization is possible
by overriding the publish method as illustrated below. This implementation
of ``Message`` is equivalent to the previous example.

.. code-block:: python

    class Message(CXXLibrary):
        recipient = Parameter(default="world", help="Name of greeting recipient.")
        sources = ["lib/message.*"]
        macros = ['RECIPIENT="{recipient}"']

        def publish(self, artifact, tools):
            with tools.cwd("{outdir}"):
                artifact.collect("*.a", "lib/")
            artifact.cxxinfo.libpaths.append("lib")
            artifact.collect("lib/*.h", "include/")
            artifact.cxxinfo.incpaths.append("include")


The ``cxxinfo`` artifact metadata can be used with other build systems too,
such as CMake, Meson and Autotools. It enables your Ninja tasks to stay oblivious to
whatever build system their dependencies use as long as binary compatibility
is guaranteed.


Parameterization
~~~~~~~~~~~~~~~~

To support build customization based on parameters, several class decorators can
be used to extend a task with conditional build attributes.

The first example uses a boolean debug parameter to disable optimizations and set a
preprocessor macro. The decorators enable Ninja to consider alternative attributes,
in addition to the default ``cxxflags`` and ``macros``. The names of alternatives
are expanded with the values of parameters. When the debug parameter is assigned the
value ``true``, the ``cxxflags_debug_true`` and ``macros_debug_true`` attributes will
be matched and included in the build. If the debug parameter value is false,
no extra flags or macros will be included because there are no ``cxxflags_debug_false``
and ``macros_debug_false`` attributes in the class.

.. code-block:: python

    @ninja.attributes.cxxflags("cxxflags_debug_{debug}")
    @ninja.attributes.macros("macros_debug_{debug}")
    class Message(ninja.CXXLibrary):
        debug = BooleanParameter()
        cxxflags_debug_true = ["-g", "-Og"]
        macros_debug_true = ["DEBUG"]
        sources = ["lib/message.*"]


The next example includes source files conditionally.


.. code-block:: python

    @ninja.attributes.sources("sources_{os}")
    class Message(ninja.CXXLibrary):
        os = Parameter(values=["linux", "windows"])
        sources = ["lib/*.cpp"]
        sources_linux = ["lib/posix/*.cpp"]
        sources_windows = ["lib/win32/*.cpp"]



Influence
~~~~~~~~~

The Ninja tasks automatically let the content of the listed header and source files
influence the task identity. However, sometimes source files may ``#include`` headers which
are not listed. This is an error which may result in objects not being correctly
recompiled when the header changes. To protect against such errors, Jolt uses output
from the compiler to ensure that files included during a compilation are properly
influencing the task.

In the example below, the header ``message.h`` is included from ``message.cpp`` but it is
not listed in ``headers``, nor in ``sources``.

.. code-block:: python

    from jolt import *
    from jolt.plugins.ninja import *

    class Message(CXXLibrary):
        sources = ["lib/message.cpp"]


This would be an error because Jolt no longer tracks the content of the ``message.h`` header
and ``message.cpp`` would not be properly recompiled. However, thanks to the builtin sanity
checks, trying to build this library would fail:


.. code-block:: bash

    $ jolt build message
    [  ERROR] Execution started (message b9961000)
    [ STDOUT] [1/2] [CXX] message.cpp
    [ STDOUT] [1/2] [AR] libmessage.a
    [WARNING] Missing influence: message.h
    [  ERROR] Execution failed after 00s (message b9961000)
    [  ERROR] task is missing source influence (message)


The solution is to ensure that the header is covered by influence, either by listing
it in ``headers`` or ``sources``, or by using an influence decorator such as
``@influence.files``.

.. code-block:: python

    class Message(CXXLibrary):
        sources = ["lib/message.h", "lib/message.cpp"]


.. code-block:: python

    from jolt import influence

    @influence.files("lib/message.h")
    class Message(CXXLibrary):
        sources = ["lib/message.cpp"]


Headers from artifacts of dependencies are exempt from the sanity checks.
They already influence the consuming task implicitly. This is also true for
files in build directories.


Compiler
~~~~~~~~

The default compiler is GCC on Linux and MSVC on Windows. To use a different
compiler, set the toolchain attribute in the task class:

.. code-block:: python

    class HelloWorld(CXXExecutable):
        sources = ["main.cpp"]

        # Use a GNU toolchain instead of the default.
        toolchain = ninja.GNUToolchain


    class HelloWorld(CXXExecutable):
        sources = ["main.cpp"]

        # Use MSVC instead of the default.
        toolchain = ninja.MSVCToolchain


The compiler can be further customized by settings different environment variables,
either on the command line or through task artifact metadata.

Available environment variables:

  .. list-table::
    :widths: 20 80
    :header-rows: 1
    :class: tight-table

    * - Variable
      - Description

    * - AR
      - Archiver.

    * - AS
      - Assembler.

    * - ASFLAGS
      - Assembler flags.

    * - CC
      - C compiler.

    * - CXX
      - C++ compiler.

    * - CFLAGS
      - C compiler flags.

    * - CXXFLAGS
      - C++ compiler flags.

    * - LD
      - Linker.

    * - LDFLAGS
      - Linker flags.


The environment variables can be set through an artifact's ``environ`` attribute.
Such metadata is automatically applied to consumer compilation tasks and take
precedence over the default environment variables.

In this example, the ``compiler`` task sets environment variables for the
``helloworld`` task and makes it use the Clang compiler instead of the default.

.. code-block:: python

    class Compiler(Task):
        def publish(self, artifact, tools):
            artifact.environ.CC = "clang"
            artifact.environ.CXX = "clang++"
            artifact.environ.CFLAGS = "-g -Og"
            artifact.environ.CXXFLAGS = "-g -Og"

    class HelloWorld(CXXExecutable):
        requires = ["compiler"]
        sources = ["main.cpp"]


The example above can be extended to allow the user to override the compiler
from the command line. A ``variant`` parameter can be used to select the compiler
from a list of predefined compilers. The ``publish`` method in turn sets the
environment variables based on the value of the ``variant`` parameter.

.. code-block:: python

    class Compiler(Task):
        variant = Parameter("clang", values=["clang", "gcc"])

        def publish(self, artifact, tools):
            if self.variant == "clang":
                artifact.environ.CC = "clang"
                artifact.environ.CXX = "clang++"
            if self.variant == "gcc":
                artifact.environ.CC = "gcc"
                artifact.environ.CXX = "g++"

The default ``variant`` parameter value can be overridden from the command
line. For example, to build the ``helloworld`` task using GCC:

.. code-block:: bash

    $ jolt build helloworld -d compiler:variant=gcc

The ``-d compiler:variant=gcc`` command line argument instructs Jolt to overide
the default value of the ``variant`` parameter in the ``compiler`` task. The new
value changes the identity hash of the compiler artifact which triggers a
rebuild of all depending tasks.

This approach with default valued parameters can also be used to enable other
use-cases where you temporarily may want:

  - cross-compilation to different architectures
  - code coverage builds
  - builds with custom flags

Another similar approach is to pass the compiler as a parameter directly to
the compilation task. We introduce a base class that can be shared
by all our compilation tasks. It defines the compiler parameter and requires
the compiler task. The parameter is then used to select the compiler from the
command line:

.. code-block:: python

    @attributes.requires("requires_base")
    class ExecutableBase(CXXExecutable):
        abstract = True
        compiler = Parameter("clang", values=["gcc", "clang"])
        requires_base = ["compiler:variant={compiler}"]

    class HelloWorld(ExecutableBase):
        sources = ["main.cpp"]


.. code-block:: bash

    $ jolt build helloworld:compiler=gcc


Custom Rules
~~~~~~~~~~~~

Rules are used to transform files from one type to another.
An example is the rule that compiles a C/C++ file to an object file.
Ninja tasks can be extended with additional rules beyond those
already builtin and the builtin rules may also be overridden.

To define a new rule for a type of file, assign a Rule object
to an arbitrary attribute of the compilation task being defined.
Below is an example where a rule has been added to generate Qt moc
source files from headers.


.. code-block:: python

    class MyQtProject(CXXExecutable):
        sources = ["myqtproject.h", "myqtproject.cpp"]

        moc_rule = Rule(
            command="moc -o $out $in",
            infiles=[".h"],
            outfiles=["{outdir}/{in_path}/{in_base}_moc.cpp"])


The moc rule applies to all ``.h`` header files listed as sources,
i.e. ``myqtproject.h``. It takes the input header file and generates
a corresponding moc source file, ``myqtproject_moc.cpp``.
The moc source file will then automatically be fed to the builtin
compiler rule from which the output is an object file,
``myqtproject_moc.o``.


Below, another example illustrates how to override one of the builtin
compilation rules. The example also defines an environment variable
that will be accessible to the rule.

.. code-block:: python

    class MyQtProject(CXXExecutable):
        sources = ["myqtproject.h", "myqtproject.cpp"]

        custom_cxxflags = EnvironmentVariable()

        cxx_rule = Rule(
            command="g++ $custom_cxxflags -o $out -c $in",
            infiles=[".cpp"],
            outfiles=["{outdir}/{in_path}/{in_base}{in_ext}.o"])


.. code-block:: bash

    $ CUSTOM_CXXFLAGS=-DDEBUG jolt build myqtproject


Code Coverage
~~~~~~~~~~~~~

Ninja tasks have builtin support for code coverage instrumentation,
data collection and reporting. By setting the ``coverage`` class
attribute to ``True``, instrumentation is enabled and coverage data
files will be generated when the executable is run. Currently, only
GCC/Clang toolchains are supported, not MSVC.

The coverage data can be automatically collected and processed into a
plain-text or HTML reports with the help of task class decorators. The
decorators rely on either `Gcov
<https://gcc.gnu.org/onlinedocs/gcc/Gcov.html>`_ (plain-text) or `Lcov
<https://github.com/linux-test-project/lcov>`_ (HTML) to carry out the
work.

Example:

  .. literalinclude:: ../../examples/code_coverage/coverage.jolt
     :language: python
     :caption: examples/code_coverage/coverage.jolt


Conan Package Manager
~~~~~~~~~~~~~~~~~~~~~

The Conan package manager is an excellent way to quickly obtain prebuilt binaries
of third-party libraries. It has been integrated into Jolt allowing you to seemlessly
use Conan packages with your Jolt Ninja tasks.

In the example below, Conan is used to collect the Boost C++ libraries. Boost is then
used in our example application. All build metadata is automatically configured.

.. code-block:: python

    from jolt.plugins.conan import Conan2

    class Boost(Conan2):
        requires = ["toolchain"]
        packages = ["boost/1.74.0"]

    class HelloWorld(CXXExecutable):
        requires = ["toolchain", "boost"]
        sources = ["src/main.cpp"]

With the toolchain as a dependency also for Boost, Conan will be able to fetch
the appropriate binaries that match your toolchain. If no such binaries are
available, Conan will build them for you.
