.. _configuration:

Configuration
==============


Client
------

By default, the Jolt client loads its configuration from
``$HOME/.config/jolt/config`` on Linux and
``%APPDATA%\Roaming\Jolt\config`` on Windows.

It uses this format:

.. code-block:: text

    [section]
    key = value

The configuration can be edited manually using any editor, but
the recommended way to change configuration is to use the Jolt
``config`` command. For example:

.. code-block:: bash

    $ jolt config jolt.cachesize 100G

Available sections and their respective keys are detailed below.

The ``[jolt]`` config section contains global configuration:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``cachedir``
      - String
      - | Filesystem path to a directory where the Jolt artifact cache will reside.
        | Default:

           - Linux: ``~/.cache/jolt``
           - Windows: ``%LOCALAPPDATA%/Jolt``

    * - ``cachesize``
      - String
      - | Maximum size of the local artifact cache. When this size is reached, Jolt
          will start to evict artifacts from the cache until it no longer exceeds the
          configured limit. Artifacts which are required to execute a task currently
          present in the dependency tree are never evicted. Therefore, it may not be
          possible for Jolt to evict enough artifacts to reach the limit. Consider
          this size advisory. The size is specified in bytes and SI suffixes such as
          K, M and G are supported.
        | Default: ``1G``

    * - ``colors``
      - Boolean
      - | Colorize output. When enabled, Jolt uses colors to make it easier to
          read the console log and to spot errors.
        | Default: ``true``

    * - ``default``
      - String
      - When invoked without any arguments, Jolt by default tries to build a
        task called ``default``. The name of the default task can be overridden
        by setting this configuration key.

    * - ``download``
      - Boolean
      - | Enable Jolt to download artifacts from remote storage providers when
          running tasks locally. The option has no effect on
          distributed executions.
        | Default: ``true``

    * - ``logcount``
      - Integer
      - | Number of log files to keep.
        | Default: ``100``

    * - ``logpath``
      - String
      - Location of Jolt's log files.
        | Default:

           - Linux: ``$HOME/.jolt``
           - Windows: ``%LOCALAPPDATA%/Jolt``

    * - ``upload``
      - Boolean
      - | Configures if Jolt is allowed to upload artifacts to remote storage
          providers or not when building locally. The option has no effect on
          distributed network builds.
        | Default: ``true``

    * - ``pager``
      - String
      - The pager to use, e.g. when viewing the logfile. Defaults to
        the ``PAGER`` environment variable followed by ``less``, ``more`` and ``cat``,
        in that order.

    * - ``pluginpath``
      - String
      - A list of one or more directory names, separated by colon, specifying
        additional search paths for plugins.

    * - ``shell``
      - String
      - The shell to use when entering the interactive task debug shell.

    * - ``threads``
      - Integer
      - | Used to limit the number of threads used by third party tools such as Ninja.
          The environment variable ``JOLT_THREADS`` can also be used.
        | The default value is the number of CPUs available.

Alias
^^^^^

This plugin can be used to create user-defined task aliases
through configuration keys. An alias points to one or many
other tasks. For example, to create an alias called ``deploy``
which deploys a fictitious smartphone app to all supported devices,
run:

.. code-block:: bash

    $ jolt config alias.deploy "deploy/android deploy/iphone"
    $ jolt build deploy

Alternatively, edit the configuration manually:

.. code-block:: bash

    [alias]
    deploy = deploy/android deploy/iphone

Aliases cannot be used to override the names of tasks loaded from recipes.


Allure
^^^^^^
This plugin generates an Allure test report on the outcome of executed
tasks. The report includes:

 - status of tasks, i.e. successful, failed or skipped
 - duration of tasks
 - hostname of executor
 - logs

The plugin is enabled by adding a ``[allure]`` section in
the Jolt configuration. Its dependencies must also be
installed separately:

.. code-block:: bash

  $ pip install jolt[allure]


Available configuration keys:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``loglevel``
      - String
      - | The level of detail to include in task logs: ``INFO``, ``VERBOSE`` or ``DEBUG``.
        | Default: ``INFO``

    * - ``path``
      - String
      - | Path to directory where result files are written.
        | Default: ``<workspace>/allure-results``


Autoweight
^^^^^^^^^^

The autoweight plugin automatically collects statistics about task execution times.
The data is used to assign weights to task, allowing the Jolt scheduler to favor tasks
along the critical path. This improves overall execution time in a distributed execution
configuration where many tasks are executed in parallel.

The plugin is enabled by adding an ``[autoweight]`` section in
the Jolt configuration.

These configuration keys exist:


  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``samples``
      - Integer
      - | The number of execution time samples to store per task in the database.
          Once the number is exceeded, samples are evicted in FIFO order.
        | Default: ``10``


Cache
^^^^^

The ``[cache]`` section configures a remote artifact cache. The cache
is used to store artifacts that are built by Jolt. When a task is built,
Jolt will first check the cache to see if the artifact is already present.
If it is, the artifact is downloaded and used. If not, the artifact is
built and then uploaded to the cache so that it can be shared with others.

Available configuration keys:


  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``uri``
      - String
      - | The URI of the remote artifact cache. The targeted service is expected
          to implement the default Jolt cache REST API.
        | Default: ``http://cache``


Configuration variables for the cache service itself can be found here:
:ref:`Cache <configuration-services-cache>`


Dashboard
^^^^^^^^^

The dashboard plugin automatically submits required telemetry to
the Jolt Dashboard. It should be enabled on both clients and workers.

The plugin is enabled by adding a ``[dashboard]`` section in
the Jolt configuration.

These configuration keys exist:


  .. list-table::
    :widths: 30 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Description

    * - ``uri``
      - | Base URI of the Jolt Dashboard.
        | Default: http://dashboard


Email
^^^^^

The email plugin sends an HTML email report to configured recipients
when builds have completed. The email includes a list of interpreted
errors in case of failure.

.. image:: img/email.png

The plugin is enabled by adding a ``[email]`` section in
the Jolt configuration.

These configuration keys exist:


  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``server``
      - String
      - SMTP server used to send emails.

    * - ``from``
      - String
      - Sender email address.

    * - ``to``
      - String
      - Receiver email address. May also be read from environment, e.g.
        ``{environ[GERRIT_PATCHSET_UPLOADER_EMAIL]}``. Multiple addresses should be
        separated by a single space.

    * - ``cc``
      - String
      - Carbon copy recipients.

    * - ``bcc``
      - String
      - Blind carbon copy recipients.

    * - ``stylesheet``
      - String
      - An optional custom XSLT stylesheet used to transform the
        Jolt result manifest into an HTML email.

    * - ``on_success``
      - Boolean
      - | Send emails when builds are successful.
        | Default: ``true``

    * - ``on_failure``
      - Boolean
      - | Send emails when builds failed.
        | Default: ``true``


GDB
^^^

The GDB plugin enables a new command, ``gdb``. When invoked, the command
launches GDB with an executable from the specified task's artifact. It
automatically configures the GDB sysroot based on environment variables
set in the execution environment of the task.

The plugin is enabled by adding a ``[gdb]`` section in
the Jolt configuration. No additional dependencies have to be installed.


HTTP
^^^^

The HTTP plugin implements an artifact storage provider. When used,
artifacts can be automatically uploaded to and downloaded from a configured
HTTP server when tasks are executed.

This is useful in many situations, for example:

- To support distributed task execution. Task executors must be
  able to share artifacts between each other. Using a networked storage
  provider is an easy way to meet that requirement.

- To reduce execution time by letting multiple users share the same artifact
  cache. If one user has already executed a task, its artifact is simply
  downloaded to others who attempt execution.

- To reduce the amount of disk space required locally. Jolt can be configured
  to evict artifacts more aggressively from the local cache. Artifacts will
  still be available on the server if needed.

The HTTP plugin is enabled by adding an ``[http]`` section in
the Jolt configuration.

These configuration keys exist:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``download``
      - Boolean
      - | Allow/disallow artifacts to be downloaded from the HTTP server.
        | Default: ``true``

    * - ``upload``
      - Boolean
      - | Allow/disallow artifacts to be uploaded to the HTTP server.
        | Default: ``true``

    * - ``uri``
      - String
      - | URL to the HTTP server.
        | Default: ``http://cache``

    * - ``keyring.service``
      - String
      - Keyring service identifier. Currently, only basic authentication is
        supported. Authentication is disabled if left unset.

    * - ``keyring.username``
      - String
      - Username to use when authenticating with the HTTP server.

    * - ``keyring.password``
      - String
      - Password to use when authenticating with the HTTP server. Should normally
        never need to be set in the configuration file. By default, Jolt asks
        for the password when needed and stores it in a keyring for future use.


Logstash (HTTP)
^^^^^^^^^^^^^^^

The logstash plugin is used to collect task logs into a common place. This is useful
in distributed execution environments where detailed logs may not always be immediately
accessible to ordinary users. Unlike the terminal log output, stashed logs are always
unfiltered and include statements from all log levels as well as exception callstacks.

The plugin is enabled by adding a ``[logstash]`` section in
the Jolt configuration.

These configuration keys exist:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``http.uri``
      - String
      - | An HTTP URL where logs will be stashed. The ``HTTP PUT`` method is used.
        | Default: ``http://logstash``
    * - ``failed``
      - Boolean
      - | Stash logs when tasks fail.
        | Default: ``false``
    * - ``passed``
      - Boolean
      - | Stash logs when tasks pass and finish successfully.
        | Default: ``false``


Network
^^^^^^^

The ``[network]`` section contains keys applicable when Jolt is started
in network execution mode.

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``config``
      - String
      - The ``config`` key contains config file content for Jolt to be used
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


Ninja Compilation Database
^^^^^^^^^^^^^^^^^^^^^^^^^^

This plugin enables compilation database generation for Ninja C++
tasks. The database is automatically published in task artifacts.
Note that commands are recorded exactly as invoked by Ninja and
they are therefore not immediately usable because of how Jolt
sandboxes dependencies. A special command, ``compdb`` is made
available to post-process published databases into a database that
is usable with IDEs. The command takes an already built task as
argument:

.. code-block:: bash

    $ jolt compdb <task>

Upon completion, a path to the resulting database is printed.
The database aggregates the databases of the task and all its
dependencies.

The plugin is enabled by adding a ``[ninja-compdb]`` section in
the Jolt configuration. Ninja version >= 1.10.0 is required.


Scheduler
^^^^^^^^^

The ``[scheduler]`` section configures remote task scheduling.
A remote scheduler accepts task execution requests from the Jolt client
and distributes them to workers. Logs, artifacts and results are collected
from the workers and returned to the client in real-time

Tasks can be assigned a priority. The scheduler will always attempt to
execute tasks with the highest priority first, if there is an eligible
worker available. If no worker is available, the task is queued until
one becomes available. The scheduler will also attempt to execute tasks
in the order they were submitted, but this is not guaranteed. In some cases,
competing builds with fewer remaining tasks may be prioritized.

Available configuration keys:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``uri``
      - String
      - | The URI of the scheduler service.
        | Default: ``tcp://scheduler:9090``

Configuration variables for the scheduler service itself can be found here:
:ref:`Scheduler <configuration-services-scheduler>`


Selfdeploy
^^^^^^^^^^

The Selfdeploy plugin automatically deploys the running version
of Jolt to all workers in a distrubuted execution environment.
This is useful to ensure that the same version of Jolt and its
dependencies are used everywhere when tasks are executed.

Before starting execution of a task, a network executor will
download Jolt from the configured storage provider and install
it into a virtual environment. Multiple versions can co-exist
on workers, thus avoiding manual deployment of multiple
container images in clusters.

The plugin is enabled by adding a ``[selfdeploy]`` section in
the Jolt configuration. Note that ``pip`` must be installed.

These configuration keys exist:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``extra``
      - String
      - Comma separated list of paths to additional python modules to be
        deployed. The paths should be relative to the workspace root.

Once enabled, the plugin automatically passes two build environment
parameters to the scheduler:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``jolt_url``
      - String
      - A URL to a compressed tarball with the sources of the running Jolt
        version.

    * - ``jolt_identity``
      - String
      - The identity of the Jolt artifact.

    * - ``jolt_requires``
      - String
      - A list of additional Python modules to install on the executor.


Symlinks
^^^^^^^^

The symlink plugin automatically creates symlinks to task artifacts
in the jolt workspace (relative to the topmost ``.jolt`` file). The
symlinks are kept updated and always points to the latest built
artifact.

The plugin is enabled by adding a ``[symlinks]`` section in
the Jolt configuration.

These configuration keys exist:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``path``
      - String
      - | Path, relative to the workspace root, where symlinks
          will be created.
        | Default: ``artifacts``.


Telemetry
^^^^^^^^^

The telemtry plugin posts task telemetry to a configured HTTP
endpoint. The payload is a JSON object with these fields:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Field
      - Type
      - Description

    * - ``name``
      - String
      - The name of the task.

    * - ``identity``
      - String
      - The identity of the task artifact.

    * - ``instance``
      - String
      - A UUID representing the lifecycle of the task.
        Tasks can be executed multiple times with the same identity,
        for example if the first execution attempt failed and a subsequent
        attempt succeeded. The instance ID may be used to distingush between
        such attempts.

    * - ``hostname``
      - String
      - Hostname of the machine from which the telemetry
        record originated.

    * - ``role``
      - String
      - ``client`` or ``worker`` depending on where the record originated.

    * - ``event``
      - String
      - ``queued``, ``started``, ``failed`` or ``finished``.

The plugin is enabled by adding a ``[telemetry]`` section in
the Jolt configuration.

These configuration keys exist:

  .. list-table::
    :widths: 20 10 70
    :header-rows: 1
    :class: tight-table

    * - Config Key
      - Type
      - Description

    * - ``uri``
      - String
      - Where telemetry records should be posted.

    * - ``local``
      - Boolean
      - | Submit telemetry for locally executed tasks.
        | Default: ``true``.

    * - ``network``
      - Boolean
      - | Submit telemetry for tasks executed by a network worker.
        | Default: ``true``.

    * - ``queued``
      - Boolean
      - | Enable queued event.
        | Default: ``true``.

    * - ``started``
      - Boolean
      - | Enable started event.
        | Default: ``true``.

    * - ``failed``
      - Boolean
      - | Enable failed event.
        | Default: ``true``.

    * - ``finished``
      - Boolean
      - | Enable finished event.
        | Default: ``true``.


Services
--------

All Jolt services can be deployed using container images. The following
sections detail how to configure the services using environment variables
and/or configuration files.

 .. _configuration-services-cache:

Cache
^^^^^

The cache service is used to store artifacts that are built by Jolt.
The service implements an LRU cache and will evict artifacts when the
cache exceeds a configured size. The cache is accessed using a REST API
over HTTP(S).

Its container image is available at `robrt/jolt-cache <https://hub.docker.com/r/robrt/jolt-cache>`_

The following volume mount points exist:

  .. list-table::
    :widths: 30 70
    :header-rows: 1
    :class: tight-table

    * - Volume Path
      - Description

    * - ``/data``
      - The default directory path where artifact files are stored.


The cache service can be configured using environment variables and/or a configuration file at ``/etc/jolt/cache.yaml``.

  .. list-table::
    :widths: 20 20 10 50
    :header-rows: 1
    :class: tight-table

    * - Environment Variable
      - Config File Key
      - Type
      - Description

    * - ``JOLT_CACHE_CERT``
      - ``cert``
      - String
      - | The path to the server certificate file to use if HTTPS is enabled.

    * - ``JOLT_CACHE_CERT_KEY``
      - ``cert_key``
      - String
      - | The path to the server certificate private key file to use if HTTPS is enabled.

    * - ``JOLT_CACHE_INSECURE``
      - ``insecure``
      - Boolean
      - | If set to ``true``, the cache will not use HTTPS, even if a certificate
          and key are provided.
        | Default: ``false``

    * - ``JOLT_CACHE_LISTEN_HTTP``
      - ``listen_http``
      - String
      - | The address and port on which the cache will listen for HTTP(S) requests.
        | The default is ``:8080`` for HTTP and ``:8443`` for HTTPS.

    * - ``JOLT_CACHE_MAX_SIZE``
      - ``max_size``
      - String
      - | The maximum size of the cache in bytes. This is a soft limit and
          the cache may exceed this size temporarily. The cache will start to
          evict artifacts when it exceeds this size.
        | Default: ``10GiB``

    * - ``JOLT_CACHE_PATH``
      - ``cache_path``
      - String
      - | The path to the cache directory.
        | Default: ``/data``

    * - ``JOLT_CACHE_VERBOSITY``
      - ``verbosity``
      - Integer
      - | The verbosity level of the cache. Higher value enables more detailed logs.
        | Default: ``0``

Dashboard
^^^^^^^^^

The dashboard service is used to collect and display task telemetry data
from the Jolt scheduler.

Its container image is available at `robrt/jolt-dashboard <https://hub.docker.com/r/robrt/jolt-dashboard>`_.
No configuration is currently possible.

 .. _configuration-services-scheduler:

Scheduler
^^^^^^^^^

The scheduler service is used to distribute tasks from clients to workers.
Its container image is available at `robrt/jolt-scheduler <https://hub.docker.com/r/robrt/jolt-scheduler>`_.

The scheduler can be configured using environment variables and/or a configuration file at ``/etc/jolt/scheduler.yaml``.

  .. list-table::
    :widths: 20 20 60
    :header-rows: 1
    :class: tight-table

    * - Environment Variable
      - Config File Key
      - Description

    * - ``JOLT_CACHE_URI``
      - ``cache_uri``
      - | The URI of the HTTP cache service from which the scheduler may fetch Jolt clients.
          Normally, this is not used and the scheduler instead installs the same version of
          the client from the public Python package index. However, for development
          purposes it is possible to deploy the source of the running client to the cache
          and have the scheduler fetch it from there.

        | The format is ``<scheme>://<host>:<port>`` where accepted schemes are:

        - ``tcp`` for both IPv4 and IPv6 connections
        - ``tcp4`` for only IPv4 connections
        - ``tcp6`` for only IPv6 connections

        | The default is ``tcp://cache.``.

    * - ``JOLT_CACHE_SIZE``
      - ``cache_size``
      - | The maximum size of the local cache in bytes.

        | The default is ``1000000000`` (1 GB).

    * - ``JOLT_CACHE_PATH``
      - ``cache_path``
      - | The path to the local cache directory.

        | The default is ``/var/cache/jolt``.


Worker
^^^^^^

The worker service is used to execute tasks.
Its container image is available at `robrt/jolt-worker <https://hub.docker.com/r/robrt/jolt-worker>`_.

The following volume mount points exist:

  .. list-table::
    :widths: 20 80
    :header-rows: 1
    :class: tight-table

    * - Volume Path
      - Description

    * - ``/etc/jolt/worker.yaml``
      - | The configuration file for the worker.

        | A configuration file may be used instead of environment variables.
          It uses the same key names as the environment variables, but without
          the ``JOLT_`` prefix and with lowercase letters.

    * - ``/data/cache``
      - | The directory where the local Jolt artifact cache is kept.

        | The cache may be shared between multiple workers on the same node.

    * - ``/data/ws``
      - | The working directory where tasks are executed.

        | This is where source code and intermediate build files are stored.
          The working directory is unique to each worker and should not be
          shared between workers.

        | It is recommended to use a fast SSD for the working directory.

    * - ``$HOME/.config/jolt/config``
      - | The configuration file for the Jolt client that executes tasks
          on the worker as instructed by the scheduler.

        | See :ref:`configuration` for details.


The worker can be configured using environment variables and/or a configuration file at ``/etc/jolt/worker.yaml``.

  .. list-table::
    :widths: 20 20 60
    :header-rows: 1
    :class: tight-table

    * - Environment Variable
      - Config File Key
      - Description

    * - ``JOLT_CACHE_URI``
      - ``cache_uri``
      - | The URI of the HTTP cache service from which the worker may fetch Jolt clients.
          Normally, this is not used and the worker instead installs the same version of
          the client from the public Python package index. However, for development
          purposes it is possible to deploy the source of the running client to the cache
          and have the worker fetch it from there.

        | The format is ``<scheme>://<host>:<port>`` where accepted schemes are:

        - ``tcp`` for both IPv4 and IPv6 connections
        - ``tcp4`` for only IPv4 connections
        - ``tcp6`` for only IPv6 connections

        | The default is ``tcp://cache.``.

    * - ``JOLT_PLATFORM``
      - ``platform``
      - | A list of worker properties that tasks may specify in order to run on the worker.

        | The properties are used by the scheduler to select tasks that are compatible with
          the worker. For example, a task may require a worker with a specific
          operating system or CPU architecture.

        | The format is ``<key>=<value>`` where the key is the name of the property and
          the value is its value. Multiple properties can be specified by separating them
          with a comma or space.

        | A set of default properties are always advertised:

          .. list-table::
            :widths: 20 80
            :header-rows: 1
            :class: tight-table

            * - Key
              - Value

            * - ``node.os``
              - The name of the operating system, e.g. ``linux``, ``windows``.

            * - ``node.arch``
              - The name of the CPU architecture, e.g. ``amd64``, ``arm``.

            * - ``node.cpus``
              - The number of CPUs.

            * - ``node.id``
              - A unique identifier for the server on which the worker is running.

            * - ``worker.hostname``
              - The hostname of the worker.

        | The recommandation is to use ``label`` for functional properties, for example
          ``label=compilation,label=testing``.

    * - ``JOLT_TASK_PLATFORM``
      - ``task_platform``
      - | A list of task properties that are required for tasks to run on the worker.

        | For example, the worker may reject tasks that do not have the platform
          property "label=fast".

        | The format is ``<key>=<value>`` where the key is the name of the property and
          the value is its value. Multiple properties can be specified by separating them
          with a comma or space.

        | The recommandation is to use ``label`` for functional properties.

    * - ``JOLT_SCHEDULER_URI``
      - ``scheduler_uri``
      - | The URIs of the scheduler to which the worker will connect and enlist.

        | See ``JOLT_CACHE_URI`` for format. The default is ``tcp://scheduler.:9090``.


Example configuration:

  .. code:: yaml

    # /etc/jolt/worker.yaml
    cache_uri: "tcp://cache:80"
    platform:
      - "label=compilation"
      - "label=testing"
    scheduler_uri: "tcp://scheduler:9090"
