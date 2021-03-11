

Distributed Builds
==================

To support distributed and incremental task execution in a build cluster, two things are typically needed:

 - a centralized file server where resulting task artifacts can be stored

 - workers executing tasks and uploading the artifacts to the file server

Task recipies may also have to be adapted to work in a network build environment. In particular, all task dependencies such as tools and source code repositories should be explicitly declared to allow the task to run anywhere. The more explicit the better. Your workers should be capabable of handling any workload. With proper dependency management they can provision the correct environment for any task on demand.


Deploying with Docker Swarm
---------------------------

Docker's Swarm mode is an easy to use container orchestration tool which can be used to deploy and manage a cluster of Jolt workers. In this example, the Jolt AMQP plugin is used to facilitate communication between Jolt clients and workers. The workers are deployed using the standard Jolt Docker container available in Docker Hub. RabbitMQ has been chosen as the AMQP message broker and Nginx serves as the centralized HTTP artifact cache. The Docker compose file for this setup looks like this:

  .. literalinclude:: ../docker/swarm/jolt.yaml
    :language: yaml

The Jolt workers are configured through the worker.conf file. It enables the AMQP and HTTP plugins. The hidden ``amqp-worker`` command provided by the plugin will connect to the configured AMQP message broker and start processing execution requests. The HTTP plugin will store the resulting artifacts on the configured HTTP server. Jolt clients can then download these artifacts to the local host. In the example, a simple local Docker volume is used as server storage for the artifacts. In a real deployment, you probably want to use something else.

  .. literalinclude:: ../docker/swarm/worker.conf
    :language: yaml

To deploy the system into a swarm, run:

  .. code:: bash

    $ docker stack deploy -c jolt.yaml jolt

You can then scale up the the number of workers to a number suitable for your swarm:


  .. code:: bash

    $ docker service scale jolt_worker=10

Scaling is possible even with tasks in progress as long as they don't cause any side effects. If a task is interrupted because the worker is terminated, RabbitMQ will redeliver the execution request to another worker.

The newly deployed swarm of Jolt workers is utilized by configuring the Jolt client as follows:

  .. literalinclude:: ../docker/swarm/client.conf
    :language: yaml

These configuration keys can also be set from command line:

  .. code:: bash

    $ jolt config amqp.host localhost
    $ jolt config http.uri http://localhost/

If your local machine is not part of the swarm you will need to replace ``localhost`` with the IP-address of one of the swarm nodes.

To schedule a task in the swarm, pass the --network flag to the build command:

  .. code:: bash

    $ jolt build --network <task>

Alternatively, if you are using a separate configuration file:

  .. code:: bash

    $ jolt -c client.conf build --network <task>
