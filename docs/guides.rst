User-guide
==========


Building C/C++
--------------

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

  .. literalinclude:: ../examples/code_coverage/coverage.jolt
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


Building Linux
--------------

Jolt includes task base classes that can be used to build the Linux kernel and
filesystem images. The tasks are designed to be easily extended and customizable
to fit your specific needs.

Toolchain
~~~~~~~~~

In order to build a kernel, a toolchain must be available. The toolchain is
a collection of tools and libraries required to build the kernel. The toolchain
can be installed manually or provisioned by a task.

The example below shows how to provision a toolchain using a DebianHostSdk task.
This tasks assumes that the host system is running a Debian-based Linux distribution
and that the required packages have been installed. It exports environment variables
that are used by the kernel build task to locate the toolchain.

  .. literalinclude:: ../examples/linux/sdk.jolt
    :language: python
    :caption: examples/linux/sdk.jolt

Kernel
~~~~~~

To build the kernel, define a new task that inherits the
:class:`jolt.plugins.linux.Kernel` base class available in the
`jolt.plugins.linux` module. Target architecture, defconfig and
make targets are specified as parameters from the command line. Multiple
targets can be built at once.

In the example below, a kernel build task is defined where the kernel source is cloned
from the official repository on demand.

  .. literalinclude:: ../examples/linux/kernel.jolt
    :language: python
    :caption: examples/linux/kernel.jolt

This command builds a zImage kernel image and device tree blobs for the ARM architecture
using the vexpress defconfig. The build output will be published into the task artifact.

  .. code:: bash

    $ jolt build kernel:arch=arm,defconfig=vexpress,targets=zimage+dtbs

Accepted parameter values can be displayed with:

    .. code:: bash

      $ jolt inspect kernel



Filesystem
~~~~~~~~~~

Filesystem images can be built using the :class:`jolt.plugins.linux.Initramfs`
and :class:`jolt.plugins.linux.Squashfs` base classes available in the linux
plugin module. The classes use `Podman <https://podman.io>`_ to build images. It's a daemonless container
engine for developing, managing, and running OCI containers. It uses the same
command line interface as Docker and can be used as a drop-in replacement.

The filesystem image content is defined in a ``Dockerfile`` or directly in the task class.
When building images for a different architecture than the host, the host system
must have the ``binfmt-support`` and ``qemu-static-user`` packages installed to
allow execution of foreign binaries. The packages are available in most Linux
distributions.


Initramfs
^^^^^^^^^

The next example task builds an initramfs image. The image is based on the BusyBox
userland and includes a minimal set of tools and libraries required to boot the system.

  .. literalinclude:: ../examples/linux/initramfs.jolt
    :language: python
    :caption: examples/linux/initramfs.jolt

  .. code:: bash

    $ jolt build initramfs:arch=arm

The resulting artifact contains a cpio archive (initramfs) of the built container image.


SquashFS
^^^^^^^^

It is also possible to build a SquashFS image. This image is baised on the Debian stable-slim
image and includes a minimal set of tools and libraries required to boot the system. Instead
of using systemd, the image uses finit-sysv as the init system.

  .. literalinclude:: ../examples/linux/squashfs.jolt
    :language: python
    :caption: examples/linux/squashfs.jolt

  .. code:: bash

    $ jolt build squashfs:arch=arm


Virtual Machine
~~~~~~~~~~~~~~~

To try out the kernel, initramfs and SquashFS tasks, a VM task can be created.
The VM task uses QEMU to boot the kernel and initramfs image and to mount the SquashFS image.

  .. literalinclude:: ../examples/linux/vm.jolt
    :language: python
    :caption: examples/linux/vm.jolt

To run the VM using initramfs:

  .. code:: bash

    $ jolt build vm/initramfs

With the SquashFS image:

  .. code:: bash

    $ jolt build vm/squashfs


Building with Chroot
--------------------

Jolt can use chroot environments to provide a consistent build environment
across different platforms. A chroot is typically faster to start and stop
than a Docker container, but it is less isolated and secure. The chroot
feature is not available on Windows.

The example task below creates a Docker image based on the Alpine Linux
distribution. The Dockerfile is defined in the task class. It can also
be defined in a separate file and pointed to by the ``dockerfile`` attribute.
When built, the image is extracted into a directory tree that is published
into the task artifact.

  .. literalinclude:: ../examples/chroot/alpine.jolt
    :language: python


The ''AlpineChroot'' class is a ''Chroot'' resource that can be required by
other tasks. The built directory tree chroot is automatically entered when
a consumer task is executing commands. Only one chroot environment can be
used by a task at a time. The workspace and the local artifact cache are mounted
into the chroot environment and the current user is mapped to the chroot user.

  .. literalinclude:: ../examples/chroot/task.jolt
    :language: python

  .. code:: bash

    $ jolt build task

  .. code:: bash

    [   INFO] Execution started (example d6058305)
    NAME="Alpine Linux"
    ID=alpine
    VERSION_ID=3.7.3
    PRETTY_NAME="Alpine Linux v3.7"
    HOME_URL="http://alpinelinux.org"
    BUG_REPORT_URL="http://bugs.alpinelinux.org"
    [   INFO] Execution finished after 00s (example d6058305)

A more flexible alternative to using chroots as resources is to enter the
chroot environment on demand directly in the consuming task as in the example below.
A task can then use multiple chroot environments at different times.

  .. literalinclude:: ../examples/chroot/task_alternative.jolt
    :language: python


Building with Docker
--------------------

Jolt can use Docker containers to provide a consistent build environment
across different platforms. The example task below creates a Docker image
based on the Alpine Linux distribution. The Dockerfile is defined in the
task class. It can also be defined in a separate file and pointed to by the
``dockerfile`` attribute.

  .. literalinclude:: ../examples/docker/alpine.jolt
    :language: python

The Docker image is built using the ``jolt build`` command. The image is
tagged with the name of the task and its hash identity and saved to a file
that is published into the task artifact.

  .. code:: bash

    $ jolt build alpine

The image can then be used to create a container that is used as a chroot environment
when executing tasks. The required image file is automatically loaded from the
artifact cache when the container is created. The workspace and the local artifact
cache are mounted into the container and the current user is mapped to the container
user.

  .. literalinclude:: ../examples/docker/alpine_container.jolt
    :language: python

The container is used as a resource by other tasks which means that the container
is automatically started and stopped when a consumer task is executed. Only one
container can be used by a task at a time.

  .. literalinclude:: ../examples/docker/task.jolt
    :language: python

  .. code:: bash

    $ jolt build task

  .. code:: bash

    [   INFO] Execution started (example d6058305)
    NAME="Alpine Linux"
    ID=alpine
    VERSION_ID=3.7.3
    PRETTY_NAME="Alpine Linux v3.7"
    HOME_URL="http://alpinelinux.org"
    BUG_REPORT_URL="http://bugs.alpinelinux.org"
    [   INFO] Execution finished after 00s (example d6058305)


Building with Nix
-----------------

Jolt can use the `Nix package manager <https://nixos.org/>`_ to provision build environments
with tools and dependencies for tasks to use. A list of required packages can be listed directly
in the task class.

The example task below provisions three versions of the Go programming language and uses
them to build three different versions of the same program for comparison.

  .. literalinclude:: ../examples/nix/go.jolt
    :language: python

It is important to specify a Nix channel to use. The channel is a collection of Nix packages and is used to
resolve package names to package paths and to fetch the packages from a binary cache. Without
a channel, the Nix package manager may not be able to find the packages or the environment may
not be deterministically reproducible.

It is also possible to create a Nix derivation in a separate file and use it in the
task class:

  .. literalinclude:: ../examples/nix/env.nix
    :language: python

The derivation file is pointed to by the ``nixfile`` attribute:

  .. literalinclude:: ../examples/nix/derivation.jolt
    :language: python

The Nix package manager is not available on Windows (except in WSL).

.. _container_images:

Container Images
----------------

The Jolt system is designed to be deployed as a set of containers. The following
container images are available in Docker Hub:

  .. list-table::
    :widths: 20 80
    :header-rows: 1
    :class: tight-table

    * - Image
      - Description


    * - `robrt/jolt <https://hub.docker.com/r/robrt/jolt>`_
      - Jolt client image.

    * - `robrt/jolt-cache <https://hub.docker.com/r/robrt/jolt-cache>`_
      - The HTTP-based cache service image.

    * - `robrt/jolt-dashboard <https://hub.docker.com/r/robrt/jolt-dashboard>`_
      - The dashboard web application image.

    * - `robrt/jolt-scheduler <https://hub.docker.com/r/robrt/jolt-scheduler>`_
      - The scheduler application image.

    * - `robrt/jolt-worker <https://hub.docker.com/r/robrt/jolt-worker>`_
      - The worker application image.



.. _deploying_build_cluster:

Deploying a Build Cluster
-------------------------

Jolt is designed to be deployed as a set of containers. To deploy a build
cluster you typically use a container orchestration environment such as
`Kubernetes <https://kubernetes.io/>`_ or
`Docker Swarm <https://docs.docker.com/engine/swarm/>`_.
See their respective documentation for installation instructions.

The different components of the build cluster are:

    - The Jolt scheduler, which is responsible for build and task scheduling.
    - The Jolt worker, which executes tasks as instructed by the scheduler.
    - The artifact cache, which is a HTTP server used to cache build artifacts.
    - The Jolt dashboard, which is a web application used to monitor the build cluster.

Each of the components is deployed as a separate container. Information about the
images and their configuration environment variables can be found in
:ref:`container_images`


Adapting Task Definitions
~~~~~~~~~~~~~~~~~~~~~~~~~

Task classes may have to be adapted to work in a distributed execution environment.
For example, Jolt will by default not transfer any workspace files to a worker.
Such dependencies, typically source repositories, must be listed as task requirements.
See the Jolt test suite for examples of how to do this.

Another common issue is that workers don't have the required tools installed.
Those tools should to be packaged by Jolt tasks and listed as requirements in order
to be automatically provisioned on the workers. They can also be installed manually
in the worker container image, but this is not recommended as it makes administration
of the build cluster more difficult, especially when multiple different versions
of the same tool are required.

Docker Swarm
~~~~~~~~~~~~

Docker Swarm is an easy to use container orchestration tool which can be used
to deploy and manage the Jolt build cluster. The below Docker stack yaml file
will deploy a scheduler and two workers, as well as an artifact cache.

  .. literalinclude:: ../docker/swarm/jolt.yaml
    :language: yaml

The Jolt workers are configured in the ``worker.conf`` file:

  .. literalinclude:: ../docker/swarm/worker.conf
    :language: ini

The file configures the URIs of the scheduler service and the HTTP cache.
In the example, local Docker volumes are used as storage for artifacts.
In a real deployment, persistent volumes are recommended. The administrator
should also configure the maximum size allowed for the local cache in each
node with the ``jolt.cachesize`` configuration key. If multiple workers are
deployed on the same node, the local cache may be shared between them in the
same directory. Fast SSD storage is recommended for the local cache and the
worker workspace.

To deploy the system into a swarm, run:

  .. code:: bash

    $ docker stack deploy -c jolt.yaml jolt

You can then scale up the the number of workers to a number suitable for your swarm:

  .. code:: bash

    $ docker service scale jolt_worker=10

Scaling is possible even with tasks in progress as long as they don't cause any side
effects. If a task is interrupted because the worker is terminated, the scheduler will
redeliver the task execution request to another worker.

The newly deployed build cluster is utilized by configuring the Jolt client
as follows:

  .. literalinclude:: ../docker/swarm/client.conf
    :language: ini

These configuration keys can also be set from command line:

  .. code:: bash

    $ jolt config scheduler.uri tcp://127.0.0.1
    $ jolt config http.uri http://127.0.0.1

If your local machine is not part of the swarm you will need to replace
``127.0.0.1`` with the IP-address of one of the nodes in the swarm or,
preferably, a load balancing hostname.

To execute a task in the swarm, pass the ``-n/--network`` flag to the build command:

  .. code:: bash

    $ jolt build -n <task>

Alternatively, if you are using a separate configuration file:

  .. code:: bash

    $ jolt -c client.conf build --network <task>


Kubernetes
~~~~~~~~~~~~

Kubernetes is a more complex container orchestration tool which can be used
to deploy and manage the Jolt build cluster. The below Kubernetes deployment
yaml file will deploy a scheduler, two workers, an artifact cache as well as
the dashboard. Notice inline ''FIXME'' comments in the yaml file that need to
or should be replaced with actual values.

  .. literalinclude:: ../docker/kubernetes/jolt.yaml
    :language: yaml

To deploy the system into a Kubernetes cluster, run:

  .. code:: bash

    $ kubectl apply -f jolt.yaml

You can then scale up the the number of workers to a number suitable for your cluster:

    .. code:: bash

      $ kubectl scale deployment jolt-worker --replicas=10

Scaling is possible even with tasks in progress as long as they don't cause any side
effects. If a task is interrupted because the worker is terminated, the scheduler will
redeliver the task execution request to another worker.

The newly deployed build cluster is utilized by configuring the Jolt client
as follows:

  .. literalinclude:: ../docker/kubernetes/client.conf
    :language: ini

The placeholder hosts should be replaced with the actual hostnames or IPs
of the services in the Kubernetes cluster. The services are typically exposed
through a load balancer and/or an ingress controller. Both methods are exemplified
in the yaml file, but may not work out of the box in all Kubernetes installations.
Run the following command to find the ExternalIP addresses of the services:

    .. code:: bash

      $ kubectl get services jolt-cache jolt-scheduler

The client configuration keys can also be set from command line:

    .. code:: bash

      $ jolt config scheduler.uri tcp://<scheduler-service-name-or-ip>:<port>
      $ jolt config http.uri http://<cache-service-name-or-ip>:<port>

To execute a task in the cluster, pass the ``-n/--network`` flag to the build command:

  .. code:: bash

    $ jolt build -n <task>

Alternatively, if you are using a separate configuration file:

    .. code:: bash

      $ jolt -c client.conf build --network <task>



