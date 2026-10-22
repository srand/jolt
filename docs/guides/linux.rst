Building Linux
==============

Jolt includes task base classes that can be used to build the Linux kernel and
filesystem images. The tasks are designed to be easily extended and customizable
to fit your specific needs.

Toolchain
~~~~~~~~~

In order to build a kernel, a toolchain must be available. The toolchain is
a collection of tools and libraries required to build the kernel. The toolchain
can be installed manually or provisioned by a task.

The example below shows how to provision a toolchain using a DebianHostSdk task.
This tasks assumes that the host system is running a Debian-based Linux distribution
and that the required packages have been installed. It exports environment variables
that are used by the kernel build task to locate the toolchain.

  .. literalinclude:: ../../examples/linux/sdk.jolt
    :language: python
    :caption: examples/linux/sdk.jolt

Kernel
~~~~~~

To build the kernel, define a new task that inherits the
:class:`jolt.plugins.linux.Kernel` base class available in the
`jolt.plugins.linux` module. Target architecture, defconfig and
make targets are specified as parameters from the command line. Multiple
targets can be built at once.

In the example below, a kernel build task is defined where the kernel source is cloned
from the official repository on demand.

  .. literalinclude:: ../../examples/linux/kernel.jolt
    :language: python
    :caption: examples/linux/kernel.jolt

This command builds a zImage kernel image and device tree blobs for the ARM architecture
using the vexpress defconfig. The build output will be published into the task artifact.

  .. code:: bash

    $ jolt build kernel:arch=arm,defconfig=vexpress,targets=zimage+dtbs

Accepted parameter values can be displayed with:

    .. code:: bash

      $ jolt inspect kernel



Filesystem
~~~~~~~~~~

Filesystem images can be built using the :class:`jolt.plugins.linux.Initramfs`
and :class:`jolt.plugins.linux.Squashfs` base classes available in the linux
plugin module. The classes use `Podman <https://podman.io>`_ to build images. It's a daemonless container
engine for developing, managing, and running OCI containers. It uses the same
command line interface as Docker and can be used as a drop-in replacement.

The filesystem image content is defined in a ``Dockerfile`` or directly in the task class.
When building images for a different architecture than the host, the host system
must have the ``binfmt-support`` and ``qemu-static-user`` packages installed to
allow execution of foreign binaries. The packages are available in most Linux
distributions.


Initramfs
^^^^^^^^^

The next example task builds an initramfs image. The image is based on the BusyBox
userland and includes a minimal set of tools and libraries required to boot the system.

  .. literalinclude:: ../../examples/linux/initramfs.jolt
    :language: python
    :caption: examples/linux/initramfs.jolt

  .. code:: bash

    $ jolt build initramfs:arch=arm

The resulting artifact contains a cpio archive (initramfs) of the built container image.


SquashFS
^^^^^^^^

It is also possible to build a SquashFS image. This image is baised on the Debian stable-slim
image and includes a minimal set of tools and libraries required to boot the system. Instead
of using systemd, the image uses finit-sysv as the init system.

  .. literalinclude:: ../../examples/linux/squashfs.jolt
    :language: python
    :caption: examples/linux/squashfs.jolt

  .. code:: bash

    $ jolt build squashfs:arch=arm


Virtual Machine
~~~~~~~~~~~~~~~

To try out the kernel, initramfs and SquashFS tasks, a VM task can be created.
The VM task uses QEMU to boot the kernel and initramfs image and to mount the SquashFS image.

  .. literalinclude:: ../../examples/linux/vm.jolt
    :language: python
    :caption: examples/linux/vm.jolt

To run the VM using initramfs:

  .. code:: bash

    $ jolt build vm/initramfs

With the SquashFS image:

  .. code:: bash

    $ jolt build vm/squashfs
