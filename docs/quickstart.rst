Quickstart
==========

Let's kick off with a few examples, getting more into details as we move along. 

First example
--------------

Our first example is a classic. Copy/paste the code below into a file called 
``first_example.jolt``.

.. code-block:: python

    from tasks import *
    
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

    from tasks import *
    
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


Using Parameters
----------------

Next, we're going to use a task parameter to alter the ``Hello world!`` 
message. Instead of greeting the world, we'll allow the executor to specify
an alternative recipient. We rename the class to reflect this change and 
we also add a parameter class attribute. The ``run`` method is changed to 
use the new parameter's value when writing the ``message.txt`` file. 

.. code-block:: python

    class Hello(Task):
        """ Creates a text file with cheerful message """

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

    $ jolt build hello:name=John


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


