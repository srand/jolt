Plugins
=======

Jolt is extensible through plugins.


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

The Artifactory plugin is enabled by adding an ``[artifactory]`` section in
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

* ``uri`` -
  URL to the Artifactory server.

* ``keyring.username`` -
  Username to use when authenticating with Artifactory.

* ``keyring.password`` -
  Password to use when authenticating with Artifactory. Should normally
  never need to be set in the configuration file. By default, Jolt asks
  for the password when needed and stores it in a keyring for future use.

* ``keyring.service`` -
  Keyring service identifier. Defaults to ``artifactory``.


Autoweight
----------

The autoweight plugin automatically collects statistics about task execution times.
The data is used to assign weights to task, allowing the Jolt scheduler to favor tasks
along the critical path. This improves overall execution time in a distributed execution
configuration where many tasks are executed in parallel.

The plugin is enabled by adding an ``[autoweight]`` section in
the Jolt configuration.

These configuration keys exist:

* ``samples`` - Integer. The number of execution time samples to store per task in the database. Once the number is exceeded, samples are evicted in FIFO order.


FTP
-----------

The FTP plugin implements an artifact storage provider. When used,
artifacts can be automatically uploaded to and downloaded from a configured
FTP server when tasks are executed.

The plugin is enabled by adding an ``[ftp]`` section in
the Jolt configuration.

These configuration keys exist:

* ``download`` -
  Boolean. Allow/disallow artifacts to be downloaded from the FTP server.
  Defaults to ``true``.

* ``host`` -
  Hostname/IP address of the FTP server.

* ``path`` -
  Path to directory where artifacts should be stored on the FTP server.
  Defaults to ``jolt``. The directory is created if it doesn't exist.

* ``tls`` -
  Use a TLS connection to the FTP server.

* ``upload`` -
  Boolean. Allow/disallow artifacts to be uploaded to the FTP server.
  Defaults to ``true``.

* ``keyring.username`` -
  Username to use when authenticating with the FTP server.

* ``keyring.password`` -
  Password to use when authenticating with the FTP server. Should normally
  never need to be set in the configuration file. By default, Jolt asks
  for the password when needed and stores it in a keyring for future use.

* ``keyring.service`` -
  Keyring service identifier. Defaults to ``ftp``.


Jenkins
-------

The Jenkins plugin implements distributed task execution. When used,
tasks can be executed by a Jenkins job. The plugin automatically
creates and manages the job, no manual configuration of the Jenkins
server is required. When a task is ready to be executed, the plugin
requests a build of the Jolt job and passes appropriate parameters
to select and build the correct task. Builds are requested in
parallel if multiple tasks are ready to be executed. Excellent
parallelism can be achieved by allowing the job to roam freely between
Jenkins slave workers.

To use this plugin, a networked artifact storage provider must also be
configured to enable Jenkins workers to share artifacts between
each other.

The plugin is enabled by adding a ``[jenkins]`` section in
the Jolt configuration.

These configuration keys exist:

* ``template`` -
  Path to a file containing a Jenkins job template. The plugin uses this
  template to create the job required to execute tasks. The job is
  automatically recreated if the template is changed or manually
  reconfigured in the Jenkins UI.
  If no template is configured, a default one is used.

* ``uri`` -
  URL to the Jenkins server.

* ``job`` -
  Name prefix of the automatically created Jenkins job. Defaults to ``Jolt``.

* ``view`` -
  Optional. Name of a Jenkins view to add the automatically created job to.
  The view must exist.

* ``workers`` -
  Optional. The maximum number of tasks Jolt is allowed to run in parallel.
  Defaults to 16.

* ``keyring.username`` -
  Username to use when authenticating with Jenkins.

* ``keyring.password`` -
  Password to use when authenticating with Jenkins. Should normally
  never need to be set in the configuration file. By default, Jolt asks
  for the password when needed and stores it in a keyring for future use.

* ``keyring.service`` -
  Keyring service identifier. Defaults to ``jenkins``.


Selfdeploy
-----------

The Selfdeploy plugin automatically deploys the running version of
Jolt into all configured artifact storage providers. This is useful
when using distributed task execution to ensure that the same
version of Jolt is used everywhere. Before starting execution of a
task, a network executor can download and install Jolt from a
storage provider.

The plugin is enabled by adding a ``[selfdeploy]`` section in
the Jolt configuration.

These configuration keys exist:

* ``extra`` -
  Comma separated list of paths to additional python modules to be
  deployed. The paths should be relative to the workspace root.

Once enabled, the plugin automatically passes two parameters to
distributed network builds:

- ``jolt_url`` -
  A URL to a compressed tarball with the sources of the running Jolt
  version.

- ``jolt_identity`` -
  The identity of the Jolt artifact.
