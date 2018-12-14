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
Try it out by running jolt:

.. code-block:: bash

    $ jolt build helloworld

The task name is derived automatically from the class name.
