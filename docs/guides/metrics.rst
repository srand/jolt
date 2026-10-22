.. _monitoring-prometheus:

Monitoring with Prometheus
==========================

The scheduler and the artifact cache both serve Prometheus metrics at
``/metrics`` on their HTTP port. You can use them to see how busy your workers
are, how many tasks are being run and how well the cache is doing. Worker
counts come from the scheduler, so there is no need to scrape the workers
themselves.

Scraping the services
---------------------

Metrics are served on the HTTP listener, not the gRPC port. The scheduler
listens on port ``8080`` by default. The cache serves metrics on whichever HTTP
or HTTPS listener it is configured with. See
:ref:`configuration-services-scheduler` and :ref:`configuration-services-cache`
for listener and TLS settings.

Listener addresses are written as ``tcp://`` URLs, for example
``listen_http: "tcp://:8080"``. They can also be set with ``JOLT_LISTEN_HTTP``
for the scheduler and ``JOLT_CACHE_LISTEN_HTTP`` for the cache. The cache uses
TLS unless ``JOLT_CACHE_INSECURE=true`` (or ``insecure: true`` in its
configuration file).

Here is a Prometheus configuration that scrapes a scheduler and a cache every
15 seconds, both on plain HTTP port ``8080``:

.. code-block:: yaml

    scrape_configs:
      - job_name: jolt-scheduler
        scrape_interval: 15s
        metrics_path: /metrics
        static_configs:
          - targets: ["scheduler.example.com:8080"]
            labels:
              cluster: jolt-production

      - job_name: jolt-cache
        scrape_interval: 15s
        metrics_path: /metrics
        static_configs:
          - targets: ["cache.example.com:8080"]
            labels:
              cluster: jolt-production

If the cache uses HTTPS, add ``scheme: https`` and a ``tls_config`` with your
CA certificate. Keep the metrics endpoints on an internal network rather than
exposing them publicly.

In Kubernetes, scrape each scheduler and cache pod directly, for example with a
``PodMonitor`` or ``ServiceMonitor`` if you use Prometheus Operator. Don't
scrape a load-balanced service address that fronts several replicas. Each scrape
could then hit a different replica, and the counters would jump around.

The ``cluster`` label in the example is optional, but it helps if you run more
than one Jolt deployment. The queries below assume a single cluster. Add
``{cluster="jolt-production"}`` to them if you have several.

You can check that an endpoint works with curl:

.. code-block:: bash

    curl --fail http://scheduler.example.com:8080/metrics
    curl --fail http://cache.example.com:8080/metrics

Prometheus also records an ``up`` metric for every target, so
``up{job="jolt-scheduler"} == 0`` tells you when the scheduler can't be
scraped. It only tells you that the endpoint answered, not that builds are
working.

Gauges and counters
-------------------

Gauges show a current value, such as the number of connected workers or the
cache size. Counters only go up and start over from zero when the service
restarts. Use ``rate()`` or ``increase()`` on counters rather than looking at
the raw value. When you have several instances, apply ``rate()`` first and
``sum()`` second, so that a restart of one instance doesn't skew the result.

Gauges are sampled at scrape time, so anything shorter than the scrape interval
may be missed. The cache gauges are rebuilt from storage when the cache
restarts, but the hit and miss counters start over.

Scheduler metrics
-----------------

.. list-table:: Scheduler metrics
   :widths: 40 10 50
   :header-rows: 1

   * - Metric
     - Type
     - Description
   * - ``jolt_scheduler_builds``
     - Gauge
     - The total number of builds currently running.
   * - ``jolt_scheduler_builds_total``
     - Counter
     - The total number of completed builds.
   * - ``jolt_scheduler_tasks_queued``
     - Gauge
     - The total number of tasks currently queued.
   * - ``jolt_scheduler_tasks_running``
     - Gauge
     - The total number of tasks currently running.
   * - ``jolt_scheduler_tasks_failed_total``
     - Counter
     - The total number of failed tasks.
   * - ``jolt_scheduler_tasks_passed_total``
     - Counter
     - The total number of successful tasks.
   * - ``jolt_scheduler_tasks_total``
     - Counter
     - The total number of completed tasks.
   * - ``jolt_scheduler_workers``
     - Gauge
     - The total number of workers currently connected.
   * - ``jolt_scheduler_workers_by_platform``
     - Gauge
     - The number of connected workers by OS, arch, and platform label.
   * - ``jolt_scheduler_workers_active_by_platform``
     - Gauge
     - The number of connected workers unavailable for scheduling by OS, arch,
       and platform label, including workers awaiting acknowledgement.

The task counters go up once per status update, not once per task, so a task
can be counted more than once. Use them for rates and trends rather than exact
task counts.

To see how many tasks finish per second:

.. code-block:: text

    sum(rate(jolt_scheduler_tasks_total[5m]))

.. _worker-metrics:

Worker metrics
~~~~~~~~~~~~~~

The two per-platform worker gauges have these labels:

.. list-table:: Worker metric labels
   :widths: 25 25 50
   :header-rows: 1

   * - Label
     - Worker property
     - Value
   * - ``node_os``
     - ``node.os``
     - Operating system, such as ``linux`` or ``windows``.
   * - ``node_arch``
     - ``node.arch``
     - CPU architecture, such as ``amd64`` or ``arm64``.
   * - ``platform_label``
     - ``label``
     - The worker's Jolt labels.

The values come from the worker's own platform (``JOLT_PLATFORM``), not from
``JOLT_TASK_PLATFORM``. For example, workers started with
``JOLT_PLATFORM="label=tiny"`` are reported as ``platform_label="tiny"`` and
are counted separately from ``label=signing`` workers on the same OS and
architecture. Hostnames and other properties are left out, so identical workers
are counted together. Every distinct combination of labels creates new series,
so keep the number of label combinations small.

A worker with more than one label is reported with all of its labels, sorted
and separated by commas. ``JOLT_PLATFORM="label=tiny label=signing"`` becomes
``platform_label="signing,tiny"``. The worker is counted once under that
combination, not once per label, so ``platform_label="tiny"`` won't include it.
The same applies to a worker with more than one OS or architecture, which shows
up as, for example, ``node_os="linux,windows"``. A comma or backslash inside a
label is escaped with a backslash, so ``label=signing,tiny`` becomes
``platform_label="signing\\,tiny"``.

If a worker doesn't have a property, the label is empty, for example
``platform_label=""``.

A worker is active from the moment it is assigned a build until it is free to
take another one, even if it isn't running a task at that moment. The active
count therefore shows how much of the pool is assigned work, not how much CPU
is being used.

Each OS, architecture and label combination gets a series as soon as a matching
worker connects, and the series goes away when the last such worker
disconnects. When no workers are connected, ``jolt_scheduler_workers`` is
``0`` and the per-platform gauges have no series at all.

There is no metric for idle workers, but you can subtract one gauge from the
other:

.. code-block:: text

    jolt_scheduler_workers_by_platform - jolt_scheduler_workers_active_by_platform

The fraction of workers in use on each platform:

.. code-block:: text

    jolt_scheduler_workers_active_by_platform / jolt_scheduler_workers_by_platform

The same fraction per label, across all operating systems, architectures and
schedulers:

.. code-block:: text

    sum by (platform_label) (jolt_scheduler_workers_active_by_platform)
    /
    sum by (platform_label) (jolt_scheduler_workers_by_platform)

Cache metrics
-------------

.. list-table:: Cache metrics
   :widths: 40 10 50
   :header-rows: 1

   * - Metric
     - Type
     - Description
   * - ``jolt_cache_artifacts``
     - Gauge
     - Artifacts in the cache.
   * - ``jolt_cache_size_bytes``
     - Gauge
     - Total size of the artifacts in the cache. This is not the free disk
       space.
   * - ``jolt_cache_evictions_total``
     - Counter
     - Artifacts removed to stay under the size limit.
   * - ``jolt_cache_hits_total``
     - Counter
     - Lookups that found the artifact.
   * - ``jolt_cache_misses_total``
     - Counter
     - Lookups that didn't find the artifact, including artifacts whose file is
       missing from disk.

Hits and misses are counted for both HTTP and gRPC requests. A client usually
checks whether an artifact exists before downloading it, so one download often
counts as two hits. The size limit is not enforced right away, so
``jolt_cache_size_bytes`` can briefly go over it.

The cache hit ratio across all caches:

.. code-block:: text

    sum(rate(jolt_cache_hits_total[5m]))
    /
    (sum(rate(jolt_cache_hits_total[5m])) + sum(rate(jolt_cache_misses_total[5m])))

The query returns no value when there were no lookups in the interval.

Evictions per second across all caches:

.. code-block:: text

    sum(rate(jolt_cache_evictions_total[5m]))

Jolt doesn't report CPU, memory or disk usage. Use your normal host or
Kubernetes monitoring for those.
