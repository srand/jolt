Reference
===========

Artifact
--------

.. autoclass:: jolt.Artifact
   :members: collect, copy, path, final_path, environ, strings


Context
--------

.. autoclass:: jolt.Context
   :members: items, __getitem__


Influence
---------

.. automodule:: jolt.influence
   :members: attribute, daily, environ, files, hourly, monthly, source, weekly, yearly


Parameter
---------

.. autoclass:: jolt.Parameter
   :members: __init__, __str__, is_default, get_default, get_value, set_value, is_set, is_unset


BooleanParameter
----------------

.. autoclass:: jolt.BooleanParameter
   :members: __init__, __str__, is_default, get_default, get_value, set_value, is_set, is_unset, is_true, is_false


Resource
---------

.. autoclass:: jolt.tasks.Resource
   :members: acquire, release
   :show-inheritance:


Task
----

.. autoclass:: jolt.tasks.Task
   :inherited-members: cacheble, expires, extends, fast, influence, joltdir, name, requires
   :undoc-members:
   :members: info, warn, error, run, publish, unpack


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


Test
----

.. autoclass:: jolt.tasks.Test
   :members: setup, cleanup
   :undoc-members:



Tools
-----

.. autoclass:: jolt.Tools
   :members:
   :undoc-members:
