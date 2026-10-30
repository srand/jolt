====
Jolt
====

**Build anything, once.** Jolt runs your build, test and deployment tasks,
caches what they produce, and shares the results with your whole team and CI.

.. image:: https://img.shields.io/pypi/v/jolt.svg
   :target: https://pypi.org/project/jolt/
   :alt: PyPI

.. image:: https://img.shields.io/pypi/pyversions/jolt.svg
   :target: https://pypi.org/project/jolt/
   :alt: Python versions

.. image:: https://readthedocs.org/projects/jolt/badge/?version=latest
   :target: https://jolt.readthedocs.io/
   :alt: Documentation

.. image:: https://img.shields.io/pypi/l/jolt.svg
   :target: https://github.com/srand/jolt/blob/master/LICENSE
   :alt: License

----

Tasks are plain Python classes. Jolt works out what each task depends on,
computes a fingerprint of everything that influences its output, and skips
it if that output already exists in a cache, on your machine or on a server
shared with everyone else. What has been built once is never built again,
whether by you, a colleague or a CI job. In one real-world deployment, Jolt
cut the CI build time from 10 hours to 10 minutes.

.. image:: https://raw.githubusercontent.com/srand/jolt/master/docs/img/overview.png
   :alt: Developers and CI share artifacts through a cache, and send tasks to a build cluster
   :width: 600


Highlights
==========

**Recipes in Python**
  Tasks, dependencies and parameters are Python code, so there is no new
  language to learn and no limit to what a task can do.

**Cached by content**
  A task's identity is a hash of its source, parameters, files and
  dependencies, so a cached result is only reused when nothing that matters
  has changed.

**Shared caches**
  Artifacts are uploaded to a cache server, and anyone who needs the same
  result downloads it instead of building it.

**Distributed builds**
  ``jolt build -n`` sends tasks to a cluster of workers that run them in
  parallel. The scheduler, workers and cache run as containers on Docker or
  Kubernetes.

**Over 150 packages**
  Compilers, libraries and tools, from zlib and OpenSSL to LLVM, Qt and
  gRPC, built from source and kept apart for each platform and compiler.

**One command for everything**
  C++, Rust, Go, Node.js, Python or containers: every task is built the same
  way, so nobody needs to learn the others' build tools.

**Secure by default**
  TLS between all services, tokens or single sign-on with an OpenID Connect
  provider, and builds that only their owners can stop.

**Kind to your machines**
  A built-in jobserver shares the CPUs between all builds on a machine and
  slows down before memory runs out.


Quick start
===========

Install Jolt from PyPI:

.. code:: bash

   $ pip install jolt

Write a task in a file called ``hello.jolt``:

.. code:: python

   from jolt import Task


   class Hello(Task):
       """ Says hello, and publishes it. """

       def run(self, deps, tools):
           tools.write_file("hello.txt", "Hello, world!")

       def publish(self, artifact, tools):
           artifact.collect("hello.txt")

Build it:

.. code:: bash

   $ jolt build hello
   $ jolt build hello    # Nothing to do: the artifact is already cached

Change the message, and Jolt builds it again. Change it back, and the
original artifact is used without building anything.


Examples
========

**A C++ application built with CMake**, using the fmt library from Jolt's
packages. Jolt builds fmt first, or downloads it if someone already has, and
tells CMake where to find it:

.. code:: python

   from jolt.plugins import cmake
   from jolt.pkgs import fmt


   class App(cmake.CMake):
       """ The application, in the app directory. """

       requires = ["fmt"]
       srcdir = "app"

**A web application** built with a Node.js that Jolt provides, so the build
doesn't depend on what happens to be installed on the machine:

.. code:: python

   from jolt import Task
   from jolt.pkgs import nodejs


   class WebApp(Task):
       """ Builds the web application. """

       requires = ["nodejs"]

       def run(self, deps, tools):
           with tools.cwd("webapp"):
               tools.run("npm ci")
               tools.run("npm run build")

**Parameters** select variants of a task, each cached separately:

.. code:: bash

   $ jolt build fmt:shared=true
   $ jolt display app    # Show what app depends on
   $ jolt inspect app    # Show its parameters, identity and cache status


Scaling up
==========

Point Jolt at a cache server, and everyone shares their artifacts:

.. code:: ini

   [cache]
   http_uri = https://cache.example.com:8080

Add a scheduler and workers, and builds run in the cluster:

.. code:: bash

   $ jolt build -n app

The `build cluster guide <https://jolt.readthedocs.io/en/latest/guides/build-cluster.html>`_
shows how to deploy the services on Docker or Kubernetes, and how to secure
them with TLS, tokens and single sign-on.


Installing
==========

From PyPI, for Python 3.9 or later:

.. code:: bash

   $ pip install jolt

As a Docker image:

.. code:: bash

   $ docker run robrt/jolt


Learn more
==========

- `Documentation <https://jolt.readthedocs.io/>`_: the tutorial, user guides
  and reference
- `Packages <https://jolt.readthedocs.io/en/latest/packages.html>`_: the
  packages that Jolt can build
- `Issues <https://github.com/srand/jolt/issues>`_: bugs and ideas

Jolt is free software, licensed under the GNU General Public License v2.
