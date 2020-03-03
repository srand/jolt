Architecture
============

.. architecture-alias-start

Overview
--------

Jolt is a tool executing user-defined tasks. Execution is carried out
either locally on a user's computer or remotely on clustered workers.
Different types of cluster infrastructures are supported through plugins.

When a task is executed an artifact containing files and metadata is created.
The artifact is shared among users and workers in the network by the means of
storage providers (file servers). Again, different types are supported
through plugins.

In a typical configuration, automation software such as Jenkins may trigger
tasks to be executed on a cluster of workers. Resulting artifacts are stored
on the file server, ready to be downloaded by users attempting to execute
the same tasks.

.. image:: img/overview.png


Artifact Cache
--------------

All task artifacts are stored in a local cache directory.
They are content addressable, meaning they all have a unique and
reproducible identity. This identity allows the artifacts to be
consistently exchanged between local and remote caches.

.. image:: img/caches.png

The identity is a SHA1 sum of different attributes that may influence the
output of the task, as illustrated below. Such influence includes the
source code of the task, task parameters and their assigned
values, the content of files and scm repositories, the identity of
dependency tasks, etc.

The SHA1 digest is used as a key when looking up artifacts both
locally and remotely.


Execution
---------

The diagram below illustrates what happens when a task is executed by
a user.

.. image:: img/buildflow.png

.. architecture-end
