Configuration
==============

By default, Jolt loads its configuration from ``$HOME/.config/jolt/config``.
It uses this format:

.. code-block:: text

    [section]
    key = value

All available sections and their respective keys are detailed below.


Jolt
------

The ``[jolt]`` config section contains global configuration.

* ``cachesize = <size>``

  Maximum size of the local artifact cache. When this size is reached, Jolt
  will start to evict artifacts from the cache until it no longer exceeds the
  configured limit. Artifacts which are required to execute a task currently
  present in the dependency tree are never evicted. Therefore, it may not be
  possible for Jolt to evict enough artifacts to reach the limit. Consider
  this size advisory. The size is specified in bytes and SI suffixes such as
  K, M and G are supported. Example: ``cachesize = 5G``. The default size is
  1G.

* ``colors = <boolean>``

  Colorize output. When enabled, Jolt uses colors to make it easier to
  read the console log and to spot errors. The default is ``true``.

* ``download = <boolean>``

  Configures if Jolt is allowed to download artifacts from remote storage
  providers or not when building locally. The option has no effect on
  distributed network builds. The default value is ``true``.

* ``log = <filepath>``

  Location of Jolt's logfile. By default, the logfile is written in
  ``$HOME/.jolt/jolt.log``.

* ``upload = <boolean>``

  Configures if Jolt is allowed to upload artifacts to remote storage
  providers or not when building locally. The option has no effect on
  distributed network builds. The default value is ``true``.

* ``pluginpath = <str>``

  A list of one or more directory names, separated by colon, specifying
  additional search paths for plugins.

* ``threads = <integer>``
  Used to limit the number of threads used by third party tools such as Ninja.
  The environment variable ``JOLT_THREADS`` can also be used.
  The default value is the number of CPUs available.

Network
--------

The ``[network]`` section contains keys applicable when Jolt is started
in network execution mode.

* ``config = <text>``

  The ``config`` key contains config file content for Jolt to be used
  when Jolt is executed on a different machine during distributed
  execution. The configuration is automatically passed to the remote
  worker and may contain all subsections and keys detailed in this
  document. Lines must be properly indented for the key to be
  considered multiline. Example:

  .. code-block:: text

    [network]
    config = [jolt]
             upload = true
             download = true
