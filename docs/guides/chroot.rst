Building with Chroot
====================

Jolt can use chroot environments to provide a consistent build environment
across different platforms. A chroot is typically faster to start and stop
than a Docker container, but it is less isolated and secure. The chroot
feature is not available on Windows.

The example task below creates a Docker image based on the Alpine Linux
distribution. The Dockerfile is defined in the task class. It can also
be defined in a separate file and pointed to by the ``dockerfile`` attribute.
When built, the image is extracted into a directory tree that is published
into the task artifact.

  .. literalinclude:: ../../examples/chroot/alpine.jolt
    :language: python


The ''AlpineChroot'' class is a ''Chroot'' resource that can be required by
other tasks. The built directory tree chroot is automatically entered when
a consumer task is executing commands. Only one chroot environment can be
used by a task at a time. The workspace and the local artifact cache are mounted
into the chroot environment and the current user is mapped to the chroot user.

  .. literalinclude:: ../../examples/chroot/task.jolt
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

  .. literalinclude:: ../../examples/chroot/task_alternative.jolt
    :language: python
