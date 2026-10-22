Building with Docker
====================

Jolt can use Docker containers to provide a consistent build environment
across different platforms. The example task below creates a Docker image
based on the Alpine Linux distribution. The Dockerfile is defined in the
task class. It can also be defined in a separate file and pointed to by the
``dockerfile`` attribute.

  .. literalinclude:: ../../examples/docker/alpine.jolt
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

  .. literalinclude:: ../../examples/docker/alpine_container.jolt
    :language: python

The container is used as a resource by other tasks which means that the container
is automatically started and stopped when a consumer task is executed. Only one
container can be used by a task at a time.

  .. literalinclude:: ../../examples/docker/task.jolt
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
