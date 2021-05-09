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
   :members: collect, copy, cxxinfo, environ, path, python, final_path, strings

.. reference-artifact-end

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
   :members: requires, system

.. reference-decorators-end


Download
--------

.. reference-download-start

.. autoclass:: jolt.tasks.Download
   :undoc-members:
   :members: collect, extract, url

.. reference-download-end


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


BooleanParameter
----------------

.. reference-booleanparameter-start

.. autoclass:: jolt.BooleanParameter
   :members: __bool__, __getitem__, __init__, __str__, is_default, get_default, get_value, set_value, is_set, is_unset, is_true, is_false

.. reference-booleanparameter-end


ListParameter
-------------

.. reference-listparameter-start

.. autoclass:: jolt.Parameter
   :members: __getitem__, __init__, __iter__, __len__, __str__, is_default, get_default, get_value, set_value, is_set, is_unset

.. reference-listparameter-end


Resource
---------

.. reference-resource-start

.. autoclass:: jolt.tasks.Resource
   :members: acquire, release
   :show-inheritance:

.. reference-resource-end


Task
----

.. reference-task-start

.. autoclass:: jolt.tasks.Task
   :undoc-members:
   :members: info, warning, error, run, publish, unpack


    .. attribute:: cacheable = True

       Whether the task produces an artifact or not.

    .. attribute:: expires = Immediately()

       An expiration strategy, defining when the artifact may be evicted from the cache.

       When the size of the artifact cache exceeds the configured limit
       an attempt will be made to evict artifacts from the cache. The eviction
       algorithm processes artifacts in least recently used (LRU) order until
       an expired artifact is found.

       By default, an artifact expires immediately and may be evicted at any time
       (in LRU order). An exception to this rule is if the artifact is required by
       a task in the active task set. For example, if a task A requires the output
       of task B, B will never be evicted by A while A is being executed.

       There are several expiration strategies to choose from:

       - :class:`jolt.expires.WhenUnusedFor`
       - :class:`jolt.expires.After`
       - :class:`jolt.expires.Never`

       Examples:

      .. code-block:: python

        # May be evicted if it hasn't been used for 15 days
        expires = WhenUnusedFor(days=15)

      .. code-block:: python

        # May be evicted 1h after creation
        expires = After(hours=1)

      .. code-block:: python

        # Never evicted
        expires = Never()


    .. attribute:: extends = ""

       Name of extended task.

       A task with this attribute set is called an extension. An extension
       is executed in the context of the extended task, immediately after
       the extended task has executed.

       A common use-case for extensions is to produce additional artifacts
       from the output of another task. Also, for long-running tasks, it is
       sometimes beneficial to utilize the intermediate output from an extended
       task. The extension artifact can then be acquired more cheaply than if the
       extension had performed all of the work from scratch.

       An extension can only extend one other task.

    .. attribute:: fast = False

       Indication of task speed.

       The information is used by the distributed execution strategy to
       optimize how tasks are scheduled. Scheduling tasks remotely is always
       associated with some overhead and sometimes it's beneficial to instead
       schedule fast tasks locally if possible.

       An extended task is only considered fast if all extensions are fast.

    .. attribute:: influence = []

       List of influence provider objects.

    .. attribute:: joltdir = "."

       Path to the directory of the .jolt file where the task was defined.

    .. attribute:: name

      Name of the task. Derived from class name if not set.

    .. attribute:: requires = []

       List of dependencies to other tasks.

    .. attribute:: selfsustained = False

       Consume this task independently of its requirements.

       Requirements of a self-sustained task will be pruned if the task artifact
       is present in a cache. In other words, if the task is not executed its
       requirements are considered unnecessary.

       For example, consider the task graph A -> B -> C. If B is self-sustained
       and present in a cache, C will never be executed. C will also never be a
       transitive requirement of A. If A requires C, it should be listed
       as an explicit requirement.

       Using this attribute speeds up execution and reduces network
       traffic by allowing the task graph to be reduced.

.. reference-task-end


Test
----

.. reference-test-start

.. autoclass:: jolt.tasks.Test
   :members: setup, cleanup
   :undoc-members:

.. reference-test-end


Tools
-----

.. reference-tools-start

.. autoclass:: jolt.Tools
   :members:
   :undoc-members:

.. reference-tools-end


Conan
-----

.. reference-conan-start

Conan
^^^^^^

.. reference-conan-conan-start

.. autoclass:: jolt.plugins.conan.Conan
   :members: conanfile, generators, incremental, options, packages, remotes

.. reference-conan-conan-end

.. reference-conan-end

Docker
------

.. reference--start

DockerImage
^^^^^^^^^^^

.. reference-docker-docker-start

.. autoclass:: jolt.plugins.docker.DockerImage
   :members: compression, context, dockerfile, imagefile, tag

.. reference-docker-docker-end

.. reference-docker-end


Ninja
------

.. reference-ninja-start

CXXExecutable
^^^^^^^^^^^^^

.. reference-ninja-cxxexecutable-start

.. autoclass:: jolt.plugins.ninja.CXXExecutable

  .. autoattribute:: CXXProject.asflags
  .. autoattribute:: CXXProject.binary
  .. autoattribute:: CXXProject.cflags
  .. autoattribute:: CXXProject.cxxflags
  .. autoattribute:: CXXProject.incpaths
  .. autoattribute:: CXXProject.incremental
  .. autoattribute:: CXXProject.ldflags
  .. autoattribute:: CXXProject.libpaths
  .. autoattribute:: CXXProject.libraries
  .. autoattribute:: CXXProject.macros
  .. autoattribute:: CXXExecutable.publishdir
  .. automethod:: CXXLibrary.publish
  .. automethod:: CXXProject.run
  .. autoattribute:: CXXLibrary.selfsustained
  .. automethod:: CXXProject.shell
  .. autoattribute:: CXXProject.sources
  .. autoattribute:: CXXProject.source_influence

.. reference-ninja-cxxexecutable-end

CXXLibrary
^^^^^^^^^^

.. reference-ninja-cxxlibrary-start

.. autoclass:: jolt.plugins.ninja.CXXLibrary

  .. autoattribute:: CXXProject.asflags
  .. autoattribute:: CXXProject.binary
  .. autoattribute:: CXXProject.cflags
  .. autoattribute:: CXXProject.cxxflags
  .. autoattribute:: CXXLibrary.headers
  .. autoattribute:: CXXProject.incpaths
  .. autoattribute:: CXXProject.incremental
  .. autoattribute:: CXXProject.ldflags
  .. autoattribute:: CXXProject.libpaths
  .. autoattribute:: CXXProject.libraries
  .. autoattribute:: CXXProject.macros
  .. automethod:: CXXProject.run
  .. autoattribute:: CXXLibrary.publishapi
  .. autoattribute:: CXXLibrary.publishdir
  .. automethod:: CXXLibrary.publish
  .. autoattribute:: CXXLibrary.selfsustained
  .. automethod:: CXXProject.shell
  .. autoattribute:: CXXProject.sources
  .. autoattribute:: CXXProject.source_influence


.. reference-ninja-cxxlibrary-end


Decorators
^^^^^^^^^^

.. reference-ninja-decorators-start

.. autoclass:: jolt.plugins.ninja.attributes
  :members: asflags, cflags, cxxflags, incpaths, ldflags, libpaths, libraries, macros, sources

.. reference-ninja-decorators-end


Rule
^^^^

.. reference-ninja-rule-start

.. autoclass:: jolt.plugins.ninja.Rule
  :members: __init__

.. reference-ninja-rule-end

.. reference-ninja-end
