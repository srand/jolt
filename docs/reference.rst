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


Parameter
---------

.. autoclass:: jolt.Parameter
   :members: __init__, __str__, is_default, get_default, get_value, set_value, is_set, is_unset


Resource
---------

.. autoclass:: jolt.Resource
   :members: acquire, release


Task
----

.. autoclass:: jolt.Task
   :inherited-members: cacheable
   :members: info, joltdir, warn, error, run, publish, unpack


Test
----

.. autoclass:: jolt.Test
   :members: setup, cleanup
   :undoc-members:


Tools
-----

.. autoclass:: jolt.Tools
   :members:
   :undoc-members:
