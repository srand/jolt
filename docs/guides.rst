User-guide
==========

.. _container_images:

Container Images
----------------

The Jolt container images are available on `Docker Hub <https://hub.docker.com/r/robrt>`_.


Cache
~~~~~

The cache service is an HTTP-based server for artifact sharing between
clients and workers in a build cluster. Files and objects are
automatically evicted from the cache in LRU order when the total size
reaches a configured limit. A configurable quaranteen protects
artifacts from eviction for some time after the last access.

The cache image is named
`robrt/jolt-cache <https://hub.docker.com/r/robrt/jolt-cache>`_.
It uses Debian as its base image.


Dashboard
~~~~~~~~~

The Jolt dashboard is a web application where users can monitor the build cluster in
real time. It is designed to be deployed as a container on a node in the build cluster.

No configuration of the dashboard is required.

The dashboard image is named
`robrt/jolt-dashboard <https://hub.docker.com/r/robrt/jolt-dashboard>`_.
It uses Debian as its base image.


Jolt
~~~~

The Jolt client is the command line tool that executes tasks and optionally interacts
with a scheduler in a build cluster. It is available as a container image, but is
typically installed as a standalone application on the user's machine.

The image is named `robrt/jolt <https://hub.docker.com/r/robrt/jolt>`_.
It uses Debian as its base image.


Scheduler
~~~~~~~~~

The scheduler is the central component of a build cluster. It is responsible for
distributing tasks to workers and relaying results back to clients. The current
scheduler implementation uses a priority queue in which builds are ordered by
priority and then by the number of queued tasks remaining to be executed in the build.

The scheduler image is named `robrt/jolt-scheduler <https://hub.docker.com/r/robrt/jolt-scheduler>`_.
It uses Debian as its base image.

  .. list-table::
    :widths: 20 80
    :header-rows: 1
    :class: tight-table

    * - Environment Variable
      - Description

    * - ``JOLT_CACHE_URI``
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
      - | The maximum size of the local cache in bytes.

        | The default is ``1000000000`` (1 GB).

    * - ``JOLT_CACHE_PATH``
      - | The path to the local cache directory.

        | The default is ``/var/cache/jolt``.

    * - ``JOLT_CACHE_CLEANUP``
      - | The interval in seconds between cache cleanups.

        | The default is ``3600`` (1 hour).

    * - ``JOLT_CACHE_CLEANUP_AGE``
      - | The maximum age of a cached artifact in seconds.

        | The default is ``604800`` (1 week).

    * - ``JOLT_CACHE_CLEANUP_SIZE``
      - | The maximum size of the local cache in bytes.

        | The default is ``1000000000`` (1 GB).

    * - ``JOLT_CACHE_CLEANUP_INTERVAL``
      - | The interval in seconds between cache cleanups.

        | The default is ``3600`` (1 hour).

    * - ``JOLT_CACHE_CLEANUP_THREADS``
      - | The number of threads to use for cache cleanups.

        | The default is ``1``.

    * - ``JOLT_CACHE_CLEANUP_LOG``
      -


Worker
~~~~~~

The worker is responsible for executing tasks as instructed by the scheduler. It
is designed to be deployed as a container on a node in the build cluster. The
worker will automatically enlist with the scheduler and start executing tasks.
Multiple workers can be deployed on the same node and share the same local
artifact cache.

The Jolt worker image is named `robrt/jolt-worker <https://hub.docker.com/r/robrt/jolt-worker>`_.
It uses Debian as a base image and includes the extra packages:

  - build-essential
  - git
  - ninja-build


The following volume mount points can be configured:

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


The following environment variables can be used to configure the worker:

  .. list-table::
    :widths: 20 80
    :header-rows: 1
    :class: tight-table

    * - Environment Variable
      - Description

    * - ``JOLT_CACHE_URI``
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
      - | A list of platform properties that the worker will advertise to the scheduler.

        | The properties are used by the scheduler to select workers that are capable of
          executing a task. For example, a task may require a worker with a specific
          operating system or CPU architecture.

        | The format is ``<key>=<value>`` where the key is the name of the property and
          the value is its value. Multiple properties can be specified by separating them
          with a comma or space.

        | A set of default properties are always advertised:

          - ``node.os``: The name of the operating system
          - ``node.arch``: The name of the CPU architecture
          - ``node.cpus``: The number of CPUs
          - ``node.id``: A unique identifier for the node on which the worker is running
          - ``worker.hostname``: The hostname of the worker.

        | Example: ``label=compilation,label=unittesting``

    * - ``JOLT_SCHEDULER_URI``
      - | The URIs of the scheduler to which the worker will connect and enlist.

        | See ``JOLT_CACHE_URI`` for format. The default is ``tcp://scheduler.:9090``.


The worker can also be configured through a configuration file at ``/etc/jolt/worker.yaml``.
The file uses the same key names as the environment variables, but without the ``JOLT_``
prefix and with lowercase letters.

  .. list-table::
    :widths: 20 80
    :header-rows: 1
    :class: tight-table

    * - Configuration Variable
      - Description

    * - ``cache_uri``
      - | See ``JOLT_CACHE_URI``.


    * - ``platform``
      - | See ``JOLT_PLATFORM``.

    * - ``scheduler_uri``
      - | See ``JOLT_SCHEDULER_URI``.

Example:

  .. code:: yaml

    # /etc/jolt/worker.yaml
    cache_uri: "tcp://cache.:80"
    platform:
      - "label=compilation"
      - "label=unittesting"
    scheduler_uri: "tcp://scheduler.:9090"


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
    :language: conf

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
    :language: conf

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
