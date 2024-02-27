User-guide
==========

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



