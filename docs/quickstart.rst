Tutorial
==========

Let's kick off with a few examples, getting more into details as we move along.

First example
--------------

Our first example is a classic. Copy/paste the code below into a file called
``first_example.jolt``.

.. code-block:: python

    from jolt import Task

    class HelloWorld(Task):
        def run(self, deps, tools):
            print("Hello world!")


This task will simply print "Hello world!" on the console when executed.
The task name is automatically derived from the class name, but can
be overridden by setting the ``name`` class attribute.

Now try to execute the task:

.. code-block:: bash

    $ jolt build helloworld

Once the task has been executed, executing it again won't have any effect.
This is because the task produced an empty artifact which is now stored in
the local artifact cache. When Jolt determines if a task should be executed
or not, it first calculates a task identity by hashing different attributes
that would influence the output of the task, such as:

* Source code
* Name
* Parameters
* Dependencies

When the task identity is known, Jolt searches its artifact cache for an
artifact with the same identity. If one is found, no action is taken. You can
try this out by changing the ``Hello world!`` string to something else and
executing the task again. If the string is reverted back to ``Hello world!``, the
task will regain its first identity and no action will be taken because that
artifact is still present in the cache.

To clean the local cache and remove all artifacts, run:

.. code-block:: bash

    $ jolt clean

To selectively remove a specific task's artifacts, run:

.. code-block:: bash

    $ jolt clean helloworld


Publishing Files
-----------------

Tasks that don't produce output are not very useful. Let's rework our task
to instead produce a file with the ``Hello world!`` message. We also shorten
its name to ``hello``.


.. literalinclude:: ../examples/publishing_files/publishing_files.jolt
  :language: python
  :caption: examples/publishing_files/publishing_files.jolt

The implementation of the task is now split into two methods,
``run`` and ``publish``.

The ``run`` method performs the main work of the task. It creates
a file called ``message.txt`` containing our greeting from the first example.
The file is written into a temporary build directory that will persist for
the duration of the task's execution. The directory is removed afterwards.

The ``publish`` method collects the output from the work performed by ``run``.
It does so by instructing the artifact to collect all textfiles from the build
directory.

.. code-block:: bash

    $ jolt build hello

After executing the task an artifact will be present in the local cache.
Let's investigate its contents, but first we need to know the identity of
the task in order to know what artifact to look for. Run:

.. code-block:: bash

    $ jolt inspect -a hello

The ``inspect`` command displays information about the task, including the
documentation written in its Python class implementation. We're looking for the
identity:

.. code-block:: bash

      Identity          50a215905eb28a0911ff83828ac56b542525bce4

With this identity digest at hand, we can dive into the artifact cache.
By default, the cache is located in ``$HOME/.cache/jolt``. To list the
content of the current ``hello`` artifact, run:

.. code-block:: bash

    $ ls $HOME/.cache/jolt/hello/50a215905eb28a0911ff83828ac56b542525bce4

You will see the ``message.txt`` file just created.


Parameters
----------------

Next, we're going to use a task parameter to alter the ``Hello world!``
message. Instead of greeting the world, we'll allow the executor to specify
an alternative recipient. We rename the class to reflect this change and
we also add a parameter class attribute. The ``run`` method is changed to
use the new parameter's value when writing the ``message.txt`` file.


.. literalinclude:: ../examples/parameters/parameters.jolt
  :language: python
  :caption: examples/parameters/parameters.jolt


By default, the produced message will still read ``Hello world!`` because the
default value of the ``recipient`` parameter is ``world``. To produce a different
message, try this:

.. code-block:: bash

    $ jolt build hello:recipient=John


Dependencies
------------

To better illustrate the flexibility of the new parameterized task, let's add
another task class, ``Print``, which prints the contents of the ``message.txt``
file to the console. ``Print`` will declare a dependency on ``Hello``.


.. literalinclude:: ../examples/dependencies/parameters.jolt
  :language: python
  :caption: examples/dependencies/parameters.jolt


The output from this task is not ``cacheable``, forcing the task to be
executed every time. It's dependency ``hello`` however, will only be
re-executed if its influence changes, for example by passing new values
to the ``recipient`` parameter. Try it out:

.. code-block:: bash

    $ jolt build print:recipient=John
    $ jolt build print:recipient=Lisa
    $ jolt build print:recipient=Kelly


Tools
-----

The ``run`` and ``publish`` methods take a ``tools`` argument as their
last parameter. This toolbox provides a large set of tools useful for many
different types of tasks. See the reference documentation for more information.

However, Jolt was originally created with compilation tasks in mind. Below is
a real world example of a task compiling the ``e2fsprogs`` package containing
EXT2/3/4 filesystem utility programs. It uses AutoTools to configure and
build its sources into different binary applications. Luckily, the ``tools`` object
provides utilities for building autotools projects as seen below.
In addition to AutoTools, there is also support for CMake and Meson as well as
generic support for running any third-party build tool.

.. code-block:: python

    from jolt import *
    from jolt.plugins import git


    class E2fsprogs(Task):
        """ Ext 2/3/4 filesystem utilities """

        requires = ["git:url=git://git.kernel.org/pub/scm/fs/ext2/e2fsprogs.git"]

        def run(self, deps, tools):
            ac = tools.autotools()
            ac.configure("e2fsprogs")
            ac.build()
            ac.install()

        def publish(self, artifact, tools):
            ac = tools.autotools()
            ac.publish(artifact)
            artifact.environ.PATH.append("bin")

The autotools ``ac`` object automatically creates temporary build and install
(--prefix) directories which are used when configuring, building and installing
the project. All files installed in the installation directory will be published.
Both directories are removed when execution has finished, i.e. the project
will be completely rebuilt if the task's influence changes.

The task also extends the environment of consumer tasks by adding the artifact's
``bin`` directory to the ``PATH``. That way, any task that depends on
``e2fsprogs`` will be able to run its published programs directly without
explicitly referencing the artifact where they reside. Use this method to
package tools required by other tasks.

Also, note that the task requires a ``git`` repository hosted at ``kernel.org``.
This git task, implemented by a builtin plugin, is actually not a
task but a resource. You can read more about resources next.


Resources
---------

Resources are a special kind of task only executed in the context of other
tasks. They are invoked to acquire and release a resource before and after
the execution of a task. No artifact is produced by a resource.

A common use-case for resources is to allocate and reserve equipment required
during the execution of a task. Such equipment could be a build server or
a mobile device on which to run tests.

Below is a skeleton example providing mutual exclusion:

.. code-block:: python

    from jolt import *

    class Exclusivity(Resource):
        """ Resource providing mutual exclusion to an object """

        to = Parameter(help="Name of shared object")

        def acquire(self, artifact, deps, tools):
            # TODO: Implement locking
            self.info("{to} is now locked")

        def release(self, artifact, deps, tools):
            # TODO: Implement unlocking
            self.info("{to} is now unlocked")


    class RebootDevice(Task):
        """ Reboots the specified test device """

        device = Parameter(help="Name of device to reboot")
        requires = ["exclusivity:to={device}"]
        cacheable = False

        def run(self, deps, tools):
            tools.run("ssh {device} reboot")

Tests
------

After implementing the ``e2fsprogs`` task above, the next logical step is
to write a few test-cases for the utility programs it builds. Luckily, Jolt
has integrated test support.

Test tasks are derived from the ``Test`` base class instead of ``Task`` and
they are implemented like a regular Python ``unittest.TestCase``. You can use
all assertions and decorators like you normally would. In all other respects,
a ``Test`` task behaves just like a regular ``Task``.

Below is an example:

.. code-block:: python

    from jolt import *

    class E2fsTest(Test):
        requires = ["e2fsprogs"]

        def setup(self, deps, tools):
            self.tools = tools

        def test_mke2fs(self):
            self.assertTrue(self.tools.run("mke2fs"))

        def test_badblocks(self):
            self.assertTrue(self.tools.run("badblocks"))

        def test_tune2fs(self):
            self.assertTrue(self.tools.run("tune2fs"))


Influence
---------

It is important that all attributes that define the output of a task are known
and registered to avoid false cache hits. For example, in a compilation task all
compiled source files should influence the task's identity and trigger re-execution
of the task if changed, otherwise binary compatibility will be lost quickly.

When using an external third-party build tool such as make, Jolt has no way of
knowing what source files to monitor. This information must be explicitly provided
by the task's implementor. Luckily, Jolt provides a few builtin class decorators
to make it easier.

Let's revisit the ``e2fsprogs`` task from earlier, but this time we assume that the
repository is already cloned and managed by external tools and not through the
builtin Jolt ``git`` resource. We can no longer rely on the resource to automatically
influence the hash of the task. We instead use the ``git.influence`` decorator:

.. code-block:: python

    from jolt import *
    from jolt.plugins import git

    @git.influence(path="path/to/e2fsprogs")
    class E2fsprogs(Task):
        def run(self, deps, tools):
            ac = tools.autotools()
            ac.configure("path/to/e2fsprogs")
            ac.build()
            ac.install()

The decorator adds the git repository's tree hash as hash influence.
It will also add the ``git diff`` output as influence to simplify iterative local
development.

There are a number of other useful influence decorators as well:

.. code-block:: python

    from jolt import *
    from jolt import influence
    from jolt.plugins import git

    @influence.files("path/to/e2fsprogs/*.c")
    @influence.environ("CFLAGS")
    @influence.weekly
    @influence.attribute("webstatus")
    class E2fsprogs(Task):
        @property
        def webstatus(self):
            r = requests.get("http://statusindicator/")
            return r.text

        def run(self, deps, tools):
            ac = tools.autotools()
            ac.configure("path/to/e2fsprogs")
            ac.build()
            ac.install()
            self.report()

Above, the ``git.influence`` decorator has been replaced by
``influence.files``. The result is virtually the same, the content of all files
matched by the provided pattern will influence the hash of the task. However,
the Git tree hash implementation is more effecient and faster, but it obviously
doesn't work if sources reside in a different type of repository.

The ``influence.environ`` decorator is used to influence the hash of
the task based on the value of the ``CFLAGS`` environment variable. If the
value of the variable changes the task will be re-executed.

The ``influence.weekly`` decorator adds the week number as hash influence. If nothing else
changes, the task will be re-executed once every week. This can be useful to
verify that external resources, such as files downloaded from the Internet,
are still available. Other time-based decorators include:

- ``influence.yearly``
- ``influence.montly``
- ``influence.daily``
- ``influence.hourly``

The ``influence.attribute`` decorator adds the value of an attribute or property as
hash influence. Above, the ``webstatus`` property is registered to influence the task
with data obtained from a web service. The source code of the property itself is
monitored automatically.


Ninja
-----

Ninja is a fast third-party build system. Where other build systems, such as Jolt,
are high-level languages, Ninja aims to be an assembler. Together they form a
powerful couple. Jolt has builtin Ninja tasks which automatically generate Ninja
build files and build your projects for you. All you have to do is to tell Jolt which
source files to compile. You can also define custom build rules for file types not
recognized by Jolt, see the :class:`Rule <jolt.plugins.ninja.Rule>` class.


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

    from jolt import *
    from jolt.plugins.ninja import *


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
by overriding the publish method as illustrated below. These two implementations
of ``Message`` are equivalent.

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
influence the task identity. However, sometimes source files may #include headers which
are not listed. This is an error which may result in objects not being correctly
recompiled when the header changes. To protect against such errors, Jolt uses output
from the compiler to ensure that files included during a compilation are properly
influencing the task.

In the example below, the ``message.h`` header is no longer listed in
``headers``, nor in ``sources``.

.. code-block:: python

    from jolt import *
    from jolt.plugins.ninja import *

    class Message(CXXLibrary):
        sources = ["lib/message.cpp"]


Assuming ``message.cpp`` includes ``message.h``, this would be an error because Jolt no longer
tracks the content of the ``message.h`` header and ``message.cpp`` would not be properly
recompiled. However, thanks to the builtin sanity checks, trying to build this library
would fail:


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


Headers from artifacts of dependencies are exempt from the sanity checks.
They already influence the consuming task implicitly. This is also true for
files in build directories.



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

  .. literalinclude:: ../examples/code_coverage/coverage.jolt
     :language: python
     :caption: examples/code_coverage/coverage.jolt


Toolchains
~~~~~~~~~~

Maintaining binary compatibility between libraries can be a pain. To ensure
that a chain of dependencies stay compatible you could inject a synthetic
toolchain task at the bottom of your dependency tree and use it to control
all compiler options. This methods also enables easy cross-compilation.

First, define a toolchain task:

.. code-block:: python

    class Toolchain(Task):
        arch = Parameter("i386", values=["i386", "arm"])
        host = Parameter(platform.system())
        debug = BooleanParameter(False)

        def publish(self, artifact, tools):
            if self.arch.get_value() == "arm":
                artifact.environ.CC = "arm-linux-gnueabi-gcc"
            if self.arch.get_value() == "i386":
                artifact.environ.CC = "x86_64-linux-gnu-gcc -m32"
            if self.debug.is_true:
                artifact.cxxinfo.cflags.append("-g")
                artifact.cxxinfo.cflags.append("-Og")
            else:
                artifact.cxxinfo.cflags.append("-O2")


Flags can also be exported as environment variables, ``CFLAGS``, ``CXXFLAGS``, etc.

Secondly, declare the toolchain as a dependency of all your compilation tasks:


.. code-block:: python

    class HelloWorld(CXXExecutable):
        requires = ["toolchain"]
        sources = ["src/main.cpp"]


Default toolchain parameter values can be overridden from the command line when you
need to. For example, to build the ``HelloWorld`` task for the ARM architecture, run:

.. code-block:: bash

    $ jolt build helloworld -d toolchain:arch=arm

The ``-d toolchain:arch=arm`` command line argument instructs Jolt to overide
the default value of the ``arch`` parameter of the ``toolchain`` task. The new
value changes the identity of the toolchain artifact which triggers a
rebuild of all depending tasks.

To build the ``HelloWorld`` task without optimizations and with debug information:


.. code-block:: bash

    $ jolt build helloworld -d toolchain:debug=true


This approach with default valued parameters can also be used to enable other
use-cases where you temporarily may want:

  - code coverage builds
  - builds with custom cflags
  - etc



Conan Package Manager
~~~~~~~~~~~~~~~~~~~~~

The Conan package manager is an excellent way to quickly obtain prebuilt binaries
of third-party libraries. It has been integrated into Jolt allowing you to seemlessly
use Conan packages with your Jolt Ninja tasks.

In the example below, Conan is used to collect the Boost C++ libraries. Boost is then
used in our example application. All build metadata is automatically configured.

.. code-block:: python

    from jolt.plugins.conan import Conan

    class Boost(Conan):
        requires = ["toolchain"]
        packages = ["boost/1.74.0"]

    class HelloWorld(CXXExecutable):
        requires = ["toolchain", "boost"]
        sources = ["src/main.cpp"]

With the toolchain as a dependency also for Boost, Conan will be able to fetch
the appropriate binaries that match your toolchain. If no such binaries are
available, Conan will build them for you.
