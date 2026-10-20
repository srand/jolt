.. _monitoring-prometheus:

Monitoring with Prometheus
==========================

The Jolt scheduler and artifact cache expose metrics in Prometheus text format at
``GET /metrics`` on their HTTP endpoints. Use these metrics to monitor worker-pool
utilization, task throughput and cache usage. Worker counts are exported by the
scheduler; workers do not need to be scraped individually for these counts.

Scraping the services
---------------------

Use the HTTP listener configured for each service, not its gRPC port. The
scheduler's default HTTP port is ``8080``; the cache endpoint uses its configured
HTTP or HTTPS listener. See :ref:`configuration-services-scheduler` and
:ref:`configuration-services-cache` for listener and TLS settings.

Listener addresses use ``tcp://``, for example ``listen_http: "tcp://:8080"``.
For the scheduler this is also configurable through ``JOLT_LISTEN_HTTP``; for the
cache use ``JOLT_CACHE_LISTEN_HTTP``. The cache uses TLS unless
``JOLT_CACHE_INSECURE=true`` (or ``insecure: true`` in its configuration file).

For example, the following Prometheus configuration scrapes a scheduler and a
cache every 15 seconds. Replace the example addresses with reachable addresses
for your deployment. This example assumes both services use plain HTTP on port
``8080``.

.. code-block:: yaml

    scrape_configs:
      - job_name: jolt-scheduler
        scrape_interval: 15s
        metrics_path: /metrics
        static_configs:
          - targets: ["scheduler.example.net:8080"]
            labels:
              cluster: jolt-production

      - job_name: jolt-cache
        scrape_interval: 15s
        metrics_path: /metrics
        static_configs:
          - targets: ["cache.example.net:8080"]
            labels:
              cluster: jolt-production

For an HTTPS cache listener, set ``scheme: https`` and configure Prometheus
``tls_config`` with the appropriate CA certificate and server name. Keep metrics
endpoints on a trusted network, or protect them through your deployment's access
controls; do not expose them publicly just to enable monitoring.

In Kubernetes, use pod or endpoint discovery to scrape each scheduler and cache
instance directly. If you use Prometheus Operator, configure a ``PodMonitor`` or
``ServiceMonitor`` for the HTTP port and ``/metrics`` path. Pod annotations alone
only enable scraping if your Prometheus discovery configuration recognizes them.
Do not scrape a load-balanced address as a single target for multiple replicas:
successive scrapes could observe different processes' independent counters and
gauges under the same target identity.

Add a target label such as ``cluster`` to distinguish deployments. Prometheus
also adds ``job`` and ``instance`` labels. Preserve instance identity when
calculating counter rates, and scope queries to the intended cluster. The query
examples below assume that you have selected a single cluster; add
``{cluster="jolt-production"}`` selectors when necessary.

To check a plain HTTP endpoint manually:

.. code-block:: bash

    curl --fail http://scheduler.example.net:8080/metrics
    curl --fail http://cache.example.net:8080/metrics

Prometheus supplies an ``up`` metric for each scrape target. For example,
``up{job="jolt-scheduler"} == 0`` identifies failed scheduler scrapes. This metric
reports scrape success, not whether the cluster can successfully execute builds.

Metric types and lifecycle
--------------------------

Gauges report current values, such as connected workers or cache size. Counters
accumulate events within a service instance and reset when that instance
restarts. Use ``rate(counter[5m])`` for events per second or
``increase(counter[1h])`` for events over an interval rather than subtracting raw
counter samples. Calculate rates before summing across instances so Prometheus
can account for each instance's resets.

Metrics describe the state observed at scrape time. Short-lived activity between
scrapes may not be visible in gauges. Cache gauges reflect the current artifact
index, including artifacts loaded from storage after a restart; historical cache
lookup counters are not persisted.

Scheduler metrics
-----------------

The scheduler exposes the following metrics. Except for the platform-grouped
worker gauges, these metrics have no application-defined labels.

.. list-table:: Scheduler metric reference
   :widths: 40 10 50
   :header-rows: 1

   * - Metric
     - Type
     - Meaning
   * - ``jolt_scheduler_builds``
     - Gauge
     - Builds retained by the scheduler. Includes completed builds until cleanup
       removes them.
   * - ``jolt_scheduler_builds_total``
     - Counter
     - Completed builds, including terminal builds awaiting cleanup.
   * - ``jolt_scheduler_tasks_queued``
     - Gauge
     - Queued tasks in builds that have not completed.
   * - ``jolt_scheduler_tasks_running``
     - Gauge
     - Tasks reserved for delivery to executors and not yet acknowledged, in builds
       that have not completed. Includes tasks awaiting worker deployment or
       execution; not limited to tasks whose status is running.
   * - ``jolt_scheduler_tasks_failed_total``
     - Counter
     - Task status updates classified as failed, error or unstable.
   * - ``jolt_scheduler_tasks_passed_total``
     - Counter
     - Task status updates classified as passed, skipped, uploaded or downloaded.
   * - ``jolt_scheduler_tasks_total``
     - Counter
     - Task completions counted in either the failed or successful status classes
       above. Cancelled tasks do not increment this counter.
   * - ``jolt_scheduler_workers``
     - Gauge
     - Total connected workers, without platform grouping.
   * - ``jolt_scheduler_workers_by_platform``
     - Gauge
     - Connected workers grouped by OS, architecture and Jolt label set.
   * - ``jolt_scheduler_workers_active_by_platform``
     - Gauge
     - Connected workers unavailable for scheduling, grouped by OS, architecture
       and Jolt label set. Includes workers awaiting acknowledgement.

Task counters count qualifying status updates rather than a deduplicated set of
task identities. In particular, the successful counter includes skipped tasks and
artifact transfer statuses; it is not limited to tasks executed by a worker.

For example, the task completion rate across scheduler instances is:

.. code-block:: text

    sum(rate(jolt_scheduler_tasks_total[5m]))

.. _worker-metrics:

Worker metrics
~~~~~~~~~~~~~~

The two platform-grouped worker gauges have the following labels:

.. list-table:: Worker platform labels
   :widths: 25 25 50
   :header-rows: 1

   * - Prometheus label
     - Worker property
     - Value
   * - ``node_os``
     - ``node.os``
     - Operating system, normally the worker's Go ``GOOS`` value.
   * - ``node_arch``
     - ``node.arch``
     - CPU architecture, normally the worker's Go ``GOARCH`` value.
   * - ``platform_label``
     - ``label``
     - Sorted, comma-separated set of nonempty Jolt labels.

For example, ``JOLT_PLATFORM="label=tiny"`` produces
``platform_label="tiny"``, separating those workers from workers with
``label=signing`` even when their OS and architecture match. These values come
from the worker platform, not the task restrictions configured by
``JOLT_TASK_PLATFORM``. Hostnames, worker IDs and other platform properties are
not included, so workers with the same OS, architecture and Jolt label set are
aggregated. Use a small, stable set of labels to keep the number of metric series
manageable.

Multiple Jolt labels are sorted and concatenated with commas:
``JOLT_PLATFORM="label=tiny label=signing"`` produces
``platform_label="signing,tiny"`` regardless of property order. Each worker is
counted once in its label-set group, not once per individual label. A query for
``platform_label="tiny"`` therefore does not include workers in the
``signing,tiny`` group. Empty Jolt labels are ignored; workers without nonempty
labels use ``platform_label="unknown"``. Missing or empty OS/architecture
properties are labeled ``unknown``; OS/architecture properties with multiple
values are labeled ``multiple``.

An idle worker contributes to the connected count but not the active count. An
assigned worker remains active until it becomes available for another build,
even if it is not currently executing a task. Worker utilization therefore
measures scheduling allocation, not CPU utilization.

Counts include connected workers until they are unregistered. For each connected
platform group, both gauges are emitted, including zero active counts. A group's
series disappear when its last worker disconnects. With no connected workers,
``jolt_scheduler_workers`` is zero, but the platform-grouped gauges have no
samples; absence of a platform series is not an explicit zero sample.

Available workers are not exported separately. Subtract active workers from
connected workers for each platform to calculate availability:

.. code-block:: text

    jolt_scheduler_workers_by_platform - jolt_scheduler_workers_active_by_platform

The fraction of workers in use for each platform can be queried with:

.. code-block:: text

    jolt_scheduler_workers_active_by_platform / jolt_scheduler_workers_by_platform

To compare usage by Jolt label set across operating systems, architectures and
scheduler instances:

.. code-block:: text

    sum by (platform_label) (jolt_scheduler_workers_active_by_platform)
    /
    sum by (platform_label) (jolt_scheduler_workers_by_platform)

Cache metrics
-------------

The artifact cache exposes the following metrics without application-defined
labels:

.. list-table:: Cache metric reference
   :widths: 40 10 50
   :header-rows: 1

   * - Metric
     - Type
     - Meaning
   * - ``jolt_cache_artifacts``
     - Gauge
     - Current number of indexed artifacts, including files and objects.
   * - ``jolt_cache_size_bytes``
     - Gauge
     - Current size of indexed artifacts in bytes, not filesystem capacity or
       free disk space.
   * - ``jolt_cache_evictions_total``
     - Counter
     - Artifacts counted by the LRU eviction callback.
   * - ``jolt_cache_hits_total``
     - Counter
     - Successful cache lookups, including existence checks and reads.
   * - ``jolt_cache_misses_total``
     - Counter
     - Unsuccessful cache lookups, including indexed artifacts whose backing
       file cannot be accessed.

Cache lookup counters include both HTTP and gRPC operations. They are not counts
of downloaded artifacts: existence checks and subsequent reads can each
contribute a hit. The configured cache size limit is a soft limit, so
``jolt_cache_size_bytes`` may temporarily exceed it.

The lookup hit ratio across cache instances can be queried with:

.. code-block:: text

    sum(rate(jolt_cache_hits_total[5m]))
    /
    (sum(rate(jolt_cache_hits_total[5m])) + sum(rate(jolt_cache_misses_total[5m])))

This ratio is undefined when there are no lookups in the interval. The eviction
rate across cache instances is:

.. code-block:: text

    sum(rate(jolt_cache_evictions_total[5m]))

Use host or Kubernetes monitoring alongside these metrics for worker CPU and
memory utilization, container restarts and filesystem capacity. Those resource
measurements are not provided by the Jolt metric endpoints described here.
