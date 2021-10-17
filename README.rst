Jolt
============================

.. image:: https://img.shields.io/pypi/v/jolt.svg
   :target: https://pypi.python.org/pypi/jolt/
   
.. image:: https://readthedocs.org/projects/jolt/badge/?version=latest
   :target: http://jolt.readthedocs.io/?badge=latest


Jolt is a task execution tool designed for software development tasks.
It can build your C/C++ applications and React frontends, run tests, deploy your web services, 
and much more.

Tasks are defined in Python scripts. They may be executed locally by developers or by automation software 
such as Jenkins in a continuous integration pipeline. In both cases, tasks may be distributed and executed 
in parallel in a server cluster. The output of each task is cached to reduce overall execution times on 
repeat attempts. In one real world deployment, Jolt shortend the CI build duration from 10 hours to 10 minutes
on average.
 
Example C++ application task:
  
.. code:: python
 
   class CppApp(CXXExecutable):
       """ Builds a C++ application """
       arch = Parameter(values=["arm", "x64"])
       requires = [
          "git:url=https://github.com/org/cppapp.git",
          "gcc:arch={arch},version=9.1.1",
       ]
       sources = ["cppapp/include/*.hpp", "cppapp/src/*.cpp"]

.. code:: bash
 
  $ jolt build cppapp:arch=x64


Example Node.js tasks:
       
.. code:: python
 
  class NodeJS(Download):
      """ Downloads and publishes Node.js. Adds binaries to PATH. """

      version = Parameter("14.16.1")
      url = "https://nodejs.org/dist/v{version}/node-v{version}-win-x64.zip"

      def publish(self, artifact, tools):
          super(publish).publish(artifact, tools)
          artifact.environ.PATH.append("node-v{version}-win-x64")


   class WebApp(Task):
       """ Builds a really cool WebApp """
       
       requires = [
           "git:url=https://github.com/org/webapp.git",
           "nodejs"
       ]
 
       def run(self, deps, tools):
           with tools.cwd("webapp"):
               tools.run("npm ci")
               tools.run("npm build")
   
.. code:: bash
 
  $ jolt build webapp

A common command line interface for all tasks enables developers from different 
disciplines to quickly run each others tasks without in-depth knowledge of the underlying technology - 
a C++ developer doesn't have to learn NPM and a React developer doesn't have to know anything about 
CMake, Make, MSBuild, etc. Required tools and dependencies are also provisioned automatically.

For full documentation, please visit http://jolt.readthedocs.io/


Installing
----------

Jolt is available in the Python Package Index:

.. code:: bash

  $ pip install jolt
  $ jolt

And as a Docker image:

.. code:: bash

  $ docker run robrt/jolt

A thin Python wrapper is available for the Docker images. By using it, multiple versions
of Jolt can coexist on the host since the version used is selected during runtime rather
than install time. To use a specific version in a project, add a version attribute in the
Jolt manifest. By always using a specific version cache hits become more likely.

.. code:: bash

  $ pip install jolt_docker
  $ jolt
