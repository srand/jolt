.. reference-start

Reference
===========

Alias
--------

.. reference-alias-start

.. autoclass:: jolt.Alias

    .. attribute:: name

      Name of the alias. Derived from class name if not set.

    .. attribute:: requires = []

      List of dependencies to other tasks.

.. reference-alias-end

Artifact
--------

.. reference-artifact-start

.. autoclass:: jolt.Artifact
   :members: collect, copy, cxxinfo, environ, path, paths, python, final_path, strings

.. reference-artifact-end

Chroot
------

.. reference-chroot-start

.. autoclass:: jolt.Chroot
   :members: chroot

.. reference-chroot-end

Context
--------

.. reference-context-start

.. autoclass:: jolt.Context
   :members: items, __getitem__

.. reference-context-end

Decorators
----------

.. reference-decorators-start

.. autoclass:: jolt.attributes
   :members: artifact, artifact_upload, attribute, common_metadata, environ, load, requires, system, timeout

.. reference-decorators-end


Download
--------

.. reference-download-start

.. autoclass:: jolt.tasks.Download
   :undoc-members:
   :members: collect, extract, url

.. reference-download-end


Git
---
.. reference-git-start

.. autoclass:: jolt.plugins.git.Git
   :members: hash, path, rev, url

.. reference-git-end


Influence
---------

.. reference-influence-start

.. automodule:: jolt.influence
   :members: always, attribute, daily, environ, files, hourly, monthly, weekly, yearly

.. reference-influence-end


Parameter
---------

.. reference-parameter-start

.. autoclass:: jolt.Parameter
   :members: __init__, __str__, is_default, get_default, get_value, set_value, is_set, is_unset

.. reference-parameter-end


.. reference-booleanparameter-start

.. autoclass:: jolt.BooleanParameter
   :members: __bool__, __getitem__, __init__, __str__, is_default, get_default, get_value, is_set, is_unset, is_true, is_false

.. reference-booleanparameter-end


.. reference-intparameter-start

.. autoclass:: jolt.IntParameter
   :members: __bool__, __int__, __init__, __str__, is_default, get_default, get_value, is_set, is_unset

.. reference-intparameter-end


.. reference-listparameter-start

.. autoclass:: jolt.ListParameter
   :members: __getitem__, __init__, __iter__, __len__, __str__, is_default, get_default, get_value, is_set, is_unset

.. reference-listparameter-end


Resource
---------

.. reference-resource-start

.. autoclass:: jolt.tasks.Resource
   :members: acquire, release
   :show-inheritance:

.. reference-resource-end


Runner
------

.. reference-runner-start

.. autoclass:: jolt.tasks.Runner
   :members: args, requires, shell
   :show-inheritance:

.. reference-runner-end


Script
------

.. reference-script-start

.. autoclass:: jolt.tasks.Script
   :members: collect
   :show-inheritance:

.. reference-script-end


Task
----

.. reference-task-start

.. autoclass:: jolt.tasks.Task
   :members:
   :inherited-members:

.. reference-task-end

MultiTask
---------

.. reference-multitask-start

.. autoclass:: jolt.tasks.MultiTask
   :members: call, command, generate, mkdir, mkdirname, render, render_file

.. reference-multitask-end


Test
----

.. reference-test-start

.. autoclass:: jolt.tasks.Test
   :members: setup, cleanup, parameterized
   :undoc-members:

.. reference-test-end


Tools
-----

.. reference-tools-start

.. autoclass:: jolt.Tools
   :members:
   :undoc-members:

.. reference-tools-end


CMake
-----

.. reference-cmake-start

CMake
^^^^^^

.. reference-cmake-cmake-start

.. autoclass:: jolt.plugins.cmake.CMake
   :members: cmakelists, options

.. reference-cmake-cmake-end

.. reference-cmake-end


Conan
-----

.. reference-conan-start

Conan
^^^^^

.. reference-conan-conan-start

.. autoclass:: jolt.plugins.conan.Conan2
   :members: conanfile, incremental, options, packages, remotes

.. reference-conan-conan-end

.. reference-conan-end

Docker
------

.. reference-docker-start

DockerClient
^^^^^^^^^^^^

.. reference-docker-dockerclient-start

.. autoclass:: jolt.plugins.docker.DockerClient
   :members: name, version, host, arch, url

.. reference-docker-dockerclient-end

DockerContainer
^^^^^^^^^^^^^^^

.. reference-docker-dockercontainer-start

.. autoclass:: jolt.plugins.docker.DockerContainer
   :members: arguments, cap_adds, cap_drops, entrypoint, environment, image, labels, privileged, ports, volumes, volumes_default, user

.. reference-docker-dockercontainer-end

DockerImage
^^^^^^^^^^^

.. reference-docker-dockerimage-start

.. autoclass:: jolt.plugins.docker.DockerImage
   :members: autoload, buildargs, cleanup, compression, context, dockerfile, extract, imagefile, labels, platform, pull, push, squash, tags

.. reference-docker-dockerimage-end

DockerLogin
^^^^^^^^^^^

.. reference-docker-dockerlogin-start

.. autoclass:: jolt.plugins.docker.DockerLogin
   :members: name, user, passwd

.. reference-docker-dockerlogin-end

Metadata
^^^^^^^^

.. reference-docker-artifact-start

The Docker module registers and makes available these artifact metadata attributes:

  - ``artifact.docker.load`` - List of image files to be loaded from the artifact
    into the local Docker registry when the artifact is consumed.

    Example:

    .. code-block:: python

      def publish(self, artifact, tools):
          artifact.docker.load.append("image.tar")

  - ``artifact.docker.pull`` - List of image tags to be pulled from a remote registry
    to the local Docker registry when the artifact is consumed.

    Example:

    .. code-block:: python

      def publish(self, artifact, tools):
          artifact.docker.pull.append("busybox:latest")

  - ``artifact.docker.rmi`` - List of image tags to remove from the local Docker
    registry when a consuming task has finished.

    Example:

    .. code-block:: python

      def publish(self, artifact, tools):
          artifact.docker.rmi.append("busybox:latest")


.. reference-docker-artifact-end

.. reference-docker-end



Google Test
-----------

.. reference-gtest-start

.. automodule:: jolt.plugins.googletest
   :members: break_on_failure, brief, disabled, fail_fast, filter, json_report, junit_report, repeat, seed, shuffle

.. autoclass:: jolt.plugins.googletest.GTestRunner
   :members: break_on_failure, brief, disabled, fail_fast, filter, repeat, seed, shuffle

.. reference-gtest-end


Linux
-----

.. reference-linux-start

.. autoclass:: jolt.plugins.linux.ArchParameter

.. autoclass:: jolt.plugins.linux.DebianHostSdk
   :members: arch

.. autoclass:: jolt.plugins.linux.FIT
   :members: configs, signature_key_name, signature_key_path

.. autoclass:: jolt.plugins.linux.Initramfs
   :members: arch, dockerfile

.. autoclass:: jolt.plugins.linux.Kernel
   :members: arch, configpaths, defconfig, defconfigpath, dtbs, features, loadaddr, loadaddr_fdt, srcdir, targets

.. autoclass:: jolt.plugins.linux.Module
   :members: arch, configpaths, defconfig, defconfigpath, features, srcdir, srcdir_module

.. autoclass:: jolt.plugins.linux.Qemu
   :members: arch, arguments, dtb, initrd, kernel, machine, memory, rootfs

.. autoclass:: jolt.plugins.linux.Squashfs
   :members: arch, dockerfile, size

.. autoclass:: jolt.plugins.linux.UBoot
   :members: arch, configpaths, defconfig, defconfigpath, features, srcdir, targets

.. reference-linux-end


Ninja
------

.. reference-ninja-start

CXXExecutable
^^^^^^^^^^^^^

.. reference-ninja-cxxexecutable-start

.. autoclass:: jolt.plugins.ninja.CXXExecutable

  .. autoattribute:: asflags
  .. autoattribute:: binary
  .. autoattribute:: cflags
  .. autoattribute:: coverage
  .. autoattribute:: cxxflags
  .. automethod:: debugshell
  .. autoattribute:: incpaths
  .. autoattribute:: incremental
  .. autoattribute:: ldflags
  .. autoattribute:: libpaths
  .. autoattribute:: libraries
  .. autoattribute:: macros
  .. autoattribute:: publishdir
  .. automethod:: publish
  .. automethod:: run
  .. autoattribute:: selfsustained
  .. autoattribute:: sources
  .. autoattribute:: source_influence
  .. autoattribute:: strip

.. reference-ninja-cxxexecutable-end

CXXLibrary
^^^^^^^^^^

.. reference-ninja-cxxlibrary-start

.. autoclass:: jolt.plugins.ninja.CXXLibrary

  .. autoattribute:: asflags
  .. autoattribute:: binary
  .. autoattribute:: cflags
  .. autoattribute:: coverage
  .. autoattribute:: cxxflags
  .. autoattribute:: headers
  .. autoattribute:: incpaths
  .. autoattribute:: incremental
  .. autoattribute:: ldflags
  .. autoattribute:: libpaths
  .. autoattribute:: libraries
  .. autoattribute:: macros
  .. automethod:: run
  .. autoattribute:: publishapi
  .. autoattribute:: publishdir
  .. automethod:: publish
  .. autoattribute:: selfsustained
  .. automethod:: debugshell
  .. autoattribute:: sources
  .. autoattribute:: source_influence
  .. autoattribute:: strip


.. reference-ninja-cxxlibrary-end


Decorators
^^^^^^^^^^

.. reference-ninja-decorators-start

.. autoclass:: jolt.plugins.ninja.attributes
  :members: asflags, cflags, coverage_data, coverage_report_gcov, coverage_report_lcov, cxxflags, incpaths, ldflags, libpaths, libraries, macros, sources

.. reference-ninja-decorators-end


Rule
^^^^

.. reference-ninja-rule-start

.. autoclass:: jolt.plugins.ninja.Rule
  :members: __init__

.. reference-ninja-rule-end

.. reference-ninja-end

.. reference-end
