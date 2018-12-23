Tutorial
==========

Let's kick off with a few examples, getting more into details as we move along.

First example
--------------

Our first example is a classic. Copy/paste the code below into a file called
``first_example.jolt``.

.. code-block:: python

    from jolt import *

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
the local artifact cache. When ``jolt`` determines if a task should be executed
or not, it first calculates a task identity by hashing different attributes
that would influence the output of the task, such as:

* Source code
* Name
* Parameters
* Dependencies

When the task identity is known, ``jolt`` searches its artifact cache for an
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

.. code-block:: python

    from jolt import *

    class HelloWorld(Task):
        """ Creates a text file with cheerful message """

        name = "hello"

        def run(self, deps, tools):
            with tools.builddir() as b, tools.cwd(b):
                tools.write_file("message.txt", "Hello world!")

        def publish(self, artifact, tools):
            with tools.builddir() as b, tools.cwd(b):
                artifact.collect("*.txt")

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

    $ jolt info hello

The ``info`` command shows information about the task, including the
documentation written in its Python implementation. We're looking for the
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

.. code-block:: python

    class Hello(Task):
        """ Creates a text file with a cheerful message """

        recipient = Parameter(default="world", help="Name of greeting recipient.")

        def run(self, deps, tools):
            with tools.builddir() as b, tools.cwd(b):
                tools.write_file("message.txt", "Hello {recipient}!")

        def publish(self, artifact, tools):
            with tools.builddir() as b, tools.cwd(b):
                artifact.collect("*.txt")


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

.. code-block:: python

    class Print(Task):
        """ Prints a cheerful message """

        recipient = Parameter(default="world", help="Name of greeting recipient.")
        requires = "hello:recipient={recipient}"
        cacheable = False

        def run(self, deps, tools):
            hello = deps["hello:recipient={recipient}"]
            with open(os.path.join(hello.path, "message.txt")) as f:
                print(f.read())

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
build its sources into binary application. Luckily, the ``tools`` object
provides utilities for building autotools projects as seen below.
In addition to AutoTools, there is also support for CMake as well as generic
support for running any tool.

.. code-block:: python

    from jolt import *
    from jolt.plugins import git


    class E2fsprogs(Task):
        """ Ext 2/3/4 filesystem utilities """

        requires = "git:url=git://git.kernel.org/pub/scm/fs/ext2/e2fsprogs.git"

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

The task also extends the environment of consumers by adding the artifact's
``bin`` directory to the ``PATH``. That way, any task that depends on
``e2fsprogs`` will be able to run its utility programs directly without
explicitly referencing the artifact where they reside.

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
        """ Resource providing mutual exclusion """

        object = Parameter(help="Name of shared object")

        def acquire(self, artifact, deps, tools):
            # TODO: Implement locking

        def release(self, artifact, deps, tools):
            # TODO: Implement unlocking


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
        requires = "e2fsprogs"

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

It is important to ensure that all attributes that influence a task's
identity are known and registered to avoid false cache hits. For example,
in a compilation task all compiled source files should influence the task's
identity and trigger re-execution of the task if changed. However, Jolt
has no way of knowing what source files to monitor. This information must be
explicitly provided by the task implementor. Luckily, Jolt provides a few
builtin class decorators to make it easier.
