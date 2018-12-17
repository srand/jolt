Plugins
=======

Jolt is extendible through plugins.


Artifactory
-----------

The Artifactory plugin implements an artifact storage provider. When used,
artifacts can be automatically uploaded to and downloaded from a configured
Artifactory instance when tasks are executed.

This is useful in many situations, for example:

- To support distributed task execution. Task executors must be
  able to share artifacts between each other. Using a networked storage
  provider like Artifactory is an easy way to meet that requirement.

- To reduce execution time by letting multiple users share the same artifact
  cache. If one user has already executed a task, its artifact is simply
  downloaded to others who attempt execution.

- To reduce the amount of disk space required locally. Jolt can be configured
  to evict artifacts more aggressively from the local cache. Artifacts will
  still be available on the server if needed.

The artifactory plugin is enabled by adding an ``[artifactory]`` section in
the Jolt configuration.

These configuration keys exist:

* ``download`` - 
  Boolean. Allow/disallow artifacts to be downloaded from Artifactory.
  Defaults to ``true``.

* ``repository`` -
  Name of the Artifactory repository where artifacts should be stored.
  Defaults to ``jolt``. Note that only generic repositories are supported.

* ``upload`` -
  Boolean. Allow/disallow artifacts to be uploaded to Artifactory.
  Defaults to ``true``.

* ``url`` - 
  URL to the Artifactory server. 

* ``keyring.username`` - 
  Username to use when authenticating with Artifactory.
  
* ``keyring.password`` - 
  Password to use when authenticating with Artifactory. Should normally
  never need to be set in the configuration file. By default, Jolt asks
  for the password when needed and stores it in a keyring for future use.

* ``keyring.service`` - 
  Keyring service identifier. Defaults to ``artifactory``.

