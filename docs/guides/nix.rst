Building with Nix
=================

Jolt can use the `Nix package manager <https://nixos.org/>`_ to provision build environments
with tools and dependencies for tasks to use. A list of required packages can be listed directly
in the task class.

The example task below provisions three versions of the Go programming language and uses
them to build three different versions of the same program for comparison.

  .. literalinclude:: ../../examples/nix/go.jolt
    :language: python

It is important to specify a Nix channel to use. The channel is a collection of Nix packages and is used to
resolve package names to package paths and to fetch the packages from a binary cache. Without
a channel, the Nix package manager may not be able to find the packages or the environment may
not be deterministically reproducible.

It is also possible to create a Nix derivation in a separate file and use it in the
task class:

  .. literalinclude:: ../../examples/nix/env.nix
    :language: python

The derivation file is pointed to by the ``nixfile`` attribute:

  .. literalinclude:: ../../examples/nix/derivation.jolt
    :language: python

The Nix package manager is not available on Windows (except in WSL).
