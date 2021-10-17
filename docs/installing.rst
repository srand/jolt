Installing
==========

There are several methods to install and run Jolt.


Using pip
---------

Jolt is available in the Python Package Index and can be installed using ``pip``.
You need a working installation of Python 3.8+. Plugins can have additional requirements.
Consult plugin documentation for details.

Run:

.. code-block:: bash

    $ pip install jolt
    $ jolt


Using Docker
------------

Jolt is available as Docker images in Docker Hub. You can run containers directly,
but depending on your use-case you may need to manually mount workspaces, caches
and configuration in order to successfully run tasks.

.. code-block:: bash

    $ docker run -it robrt/jolt

To make life easier for regular users, you can instead install a thin Python Docker wrapper:

.. code-block:: bash

    $ pip install jolt-docker
    $ jolt

This wrapper command will pull the latest Jolt Docker image and automatically run it with
required volumes, users, groups, etc. It allows multiple versions of Jolt to coexist
on the host since the version used is selected during runtime rather than install time.
A project may choose its desired version in its Jolt manifest.
