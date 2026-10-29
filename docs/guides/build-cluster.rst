.. _deploying_build_cluster:

Deploying a Build Cluster
=========================

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

For service metrics, worker-pool utilization and scrape configuration, see
:ref:`monitoring-prometheus`.


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


Build Parameters
~~~~~~~~~~~~~~~~

Build submissions carry the ``[params]`` section of the configuration to the
scheduler and the workers. The parameters can be used to attribute builds, for
example to a user and a CI job:

  .. code:: bash

    $ jolt -c params.username=alice -c params.origin="$BUILD_URL" build -n my-task

They can also be set in the configuration file. Values are expanded on the
client before the build is submitted, so they may refer to its environment:

  .. code:: ini

    [params]
    username = {environ[USER]}

The dashboard shows ``username`` and ``origin`` with the tasks of each
build, and other tools that follow the builds of the scheduler see all
parameters. Jolt doesn't check them: whoever submits a build can set them to
anything, so they tell you who claims to have started a build, not who did.

.. warning::

   Anyone who can see the builds of the scheduler can see their parameters.
   Don't put passwords or other secrets in ``[params]``.

Changing a parameter doesn't make Jolt rebuild tasks whose artifacts are
already in the cache, unless the task asks for it with
``@influence.config("params", "origin")``. The same tasks submitted with
different parameters are still listed as separate builds.


Docker Swarm
~~~~~~~~~~~~

Docker Swarm is an easy to use container orchestration tool which can be used
to deploy and manage the Jolt build cluster. The below Docker stack yaml file
will deploy a scheduler and two workers, as well as an artifact cache.

  .. literalinclude:: ../../docker/swarm/jolt.yaml
    :language: yaml

The Jolt workers are configured in the ``worker.conf`` file:

  .. literalinclude:: ../../docker/swarm/worker.conf
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

  .. literalinclude:: ../../docker/swarm/client.conf
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

  .. literalinclude:: ../../docker/kubernetes/jolt.yaml
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

  .. literalinclude:: ../../docker/kubernetes/client.conf
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


.. _build-cluster-auth:

Authentication
~~~~~~~~~~~~~~

Without configuration, the cache and the scheduler accept requests from
anyone who can reach them. Before exposing a build cluster to a network you
don't trust, secure the connections with TLS and authenticate clients, either
with static tokens or with the accounts of an OpenID Connect provider. The
two can be combined, with tokens for CI and workers and personal logins for
users.

.. _build-cluster-tls:

TLS
^^^

The cache and the scheduler serve TLS on both HTTP and gRPC when they are
configured with a certificate and private key (``cert`` and ``cert_key``).
Clients then connect with ``https://`` and ``tls://`` URIs:

  .. code:: ini

    [cache]
    http_uri = https://cache.example.com:8080
    grpc_uri = tls://cache.example.com:9090

    [scheduler]
    uri = tls://scheduler.example.com:9090

Clients verify the certificates of services with the authorities of the
system. For a private authority, point ``jolt.ca_cert`` or ``JOLT_CA_CERT``
to a PEM file with its certificate. Jolt, its workers, ``schedulerctl``,
fstree and the dashboard all use these settings.

Tokens are only sent over TLS, since they authenticate anyone who sees them.
For a trusted network, ``jolt.allow_insecure_token`` or
``JOLT_ALLOW_INSECURE_TOKEN`` allows sending them without it.

.. _build-cluster-tokens:

Tokens
^^^^^^

A token is a random string that grants permissions. Create one with:

  .. code:: bash

    $ jolt-cache token ci

The command prints the token and the entry for the ``auth`` section of
``cache.yaml`` or ``scheduler.yaml``. The configuration only contains the
SHA-256 hash of the token. Once any token is configured, clients without a
token have no permissions, unless ``auth.anonymous`` grants them some.

The cache grants ``read``, to download and look up artifacts, and ``write``,
to upload them. Example, where anyone may download artifacts but only CI may
upload them:

  .. code:: yaml

    # /etc/jolt/cache.yaml
    auth:
      anonymous: [read]
      tokens:
        - name: ci
          sha256: 31f69e6b9c24b00832b59b38a340b5346185c93eb9bb6bb54b2ef985aafdcb8f
          permissions: [read, write]

The scheduler grants these permissions:

  .. list-table::
    :widths: 20 80
    :header-rows: 1
    :class: tight-table

    * - Permission
      - Allows
    * - ``build``
      - Building and cancelling builds, and running their tasks. Clients that
        build also need ``read`` to see the logs of their tasks.
    * - ``worker``
      - Executing tasks, required by workers and the executors they start.
    * - ``read``
      - Listing builds and workers, following events and reading logs.
    * - ``admin``
      - Cancelling any build, rescheduling tasks and debugging the scheduler.
        Administrators also need ``read`` to list builds and workers.

Example:

  .. code:: yaml

    # /etc/jolt/scheduler.yaml
    auth:
      tokens:
        - name: developers
          sha256: 9c56cc51b374c3ba189210d5b6d4bf57790d351c96c47c02190ecf1e430635ab
          permissions: [build, read]
        - name: workers
          sha256: 4c1e0fb8de8c8e4c4f5b4ba9c3aa6a9ac5c3d7fb22bb4b8b0f4cbf5e8b0b6c3e
          permissions: [worker]

Clients send their tokens as bearer tokens:

- Jolt uses ``cache.token`` and ``scheduler.token``, or the
  ``JOLT_CACHE_TOKEN`` and ``JOLT_SCHEDULER_TOKEN`` environment variables.
- Workers use ``scheduler_token`` and ``cache_token``, and pass them on to the
  executors they start, which upload artifacts.
- ``schedulerctl`` uses ``scheduler_token`` in ``schedulerctl.yaml`` or
  ``JOLT_SCHEDULER_TOKEN``, and the dashboard ``JOLT_SCHEDULER_TOKEN``.

Task logs are opened in a browser, which asks for a user name and password.
Enter the token as the password; the user name is ignored.

.. _build-cluster-oidc:

Single Sign-On
^^^^^^^^^^^^^^

Instead of handing out tokens to users, the services can accept the ID tokens
of an OpenID Connect provider, such as Keycloak, Dex or Authentik in front of
an LDAP directory, or Microsoft Entra ID. Users sign in once with
``jolt login``, and every service verifies their tokens on its own with the
public keys of the provider. The services don't talk to the directory, and
they don't share any secret.

Register Jolt with the provider as a public client, with the OAuth device
authorization grant enabled, and configure the services to accept tokens
issued to it. Permissions are granted to all users of the provider and to the
members of groups:

  .. code:: yaml

    # /etc/jolt/cache.yaml
    auth:
      oidc:
        issuer: https://keycloak.example.com/realms/jolt
        audience: jolt
        permissions: [read]
        groups:
          - name: jolt-ci
            permissions: [write]

  .. code:: yaml

    # /etc/jolt/scheduler.yaml
    auth:
      oidc:
        issuer: https://keycloak.example.com/realms/jolt
        audience: jolt
        permissions: [build, read]
        groups:
          - name: jolt-admins
            permissions: [admin]

The services contact the provider when they verify the first token, so they
start even when it is unavailable. Tokens configured in ``auth.tokens`` keep
working alongside the provider.

Users configure the provider in the ``auth`` section and sign in:

  .. code:: bash

    $ jolt config auth.issuer https://keycloak.example.com/realms/jolt
    $ jolt login

``jolt login`` asks for the user name and password in the terminal if the
provider allows the OAuth password grant for the client. Otherwise it opens
the browser, or prints a URL and a code to enter there. The tokens are stored
in the system keyring, and Jolt refreshes them when they are about to expire,
so users stay signed in until the refresh token expires or they run
``jolt logout``. A token configured for a service takes precedence over the
login.

Notes on providers:

- **Keycloak:** Groups aren't included in tokens by default. Add a *Group
  Membership* mapper with the claim name ``groups`` and *Full group path*
  turned off to the client, or use realm roles with
  ``groups_claim: realm_access.roles``. Turn on *OAuth 2.0 Device
  Authorization Grant* for the client, and *Direct access grants* to sign in
  with a password in the terminal.
- **Dex:** Request the ``groups`` scope with ``auth.scopes``.
- **Microsoft Entra ID:** Use the issuer of your tenant,
  ``https://login.microsoftonline.com/<tenant-id>/v2.0``, and the
  application ID as the audience and ``auth.client_id``. Turn on *Allow
  public client flows* for the application. Tokens contain the IDs of groups
  rather than their names, so prefer app roles assigned to groups, with
  ``groups_claim: roles``. Users sign in with the browser, which also
  handles multi-factor authentication.
