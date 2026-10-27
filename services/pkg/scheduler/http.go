package scheduler

import (
	"fmt"
	"net/http"
	"slices"
	"strings"
)

var prometheusLabelEscaper = strings.NewReplacer("\\", "\\\\", "\"", "\\\"", "\n", "\\n")

func NewHttpHandler(scheduler Scheduler, r *http.ServeMux) {
	r.HandleFunc("GET /metrics", func(w http.ResponseWriter, req *http.Request) {
		stats := scheduler.Statistics()

		var metrics strings.Builder
		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_builds gauge")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_builds The total number of builds currently running.")
		fmt.Fprintf(&metrics, "jolt_scheduler_builds %d\n", stats.Builds)

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_builds_total counter")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_builds_total The total number of completed builds.")
		fmt.Fprintf(&metrics, "jolt_scheduler_builds_total %d\n", stats.CompletedBuilds)

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_tasks_queued gauge")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_tasks_queued The total number of tasks currently queued.")
		fmt.Fprintf(&metrics, "jolt_scheduler_tasks_queued %d\n", stats.QueuedTasks)

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_tasks_running gauge")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_tasks_running The total number of tasks currently running.")
		fmt.Fprintf(&metrics, "jolt_scheduler_tasks_running %d\n", stats.RunningTasks)

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_tasks_failed_total counter")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_tasks_failed_total The total number of failed tasks.")
		fmt.Fprintf(&metrics, "jolt_scheduler_tasks_failed_total %d\n", stats.FailedTasks)

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_tasks_passed_total counter")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_tasks_passed_total The total number of successful tasks.")
		fmt.Fprintf(&metrics, "jolt_scheduler_tasks_passed_total %d\n", stats.SuccessfulTasks)

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_tasks_total counter")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_tasks_total The total number of completed tasks.")
		fmt.Fprintf(&metrics, "jolt_scheduler_tasks_total %d\n", stats.CompletedTasks)

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_workers gauge")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_workers The total number of workers currently connected.")
		fmt.Fprintf(&metrics, "jolt_scheduler_workers %d\n", stats.Workers)

		platforms := make([]WorkerPlatform, 0, len(stats.WorkersByPlatform))
		for platform := range stats.WorkersByPlatform {
			platforms = append(platforms, platform)
		}
		slices.SortFunc(platforms, func(a, b WorkerPlatform) int {
			if order := strings.Compare(a.OS, b.OS); order != 0 {
				return order
			}
			if order := strings.Compare(a.Arch, b.Arch); order != 0 {
				return order
			}
			return strings.Compare(a.Label, b.Label)
		})
		platformLabels := make([]string, len(platforms))
		for i, platform := range platforms {
			platformLabels[i] = fmt.Sprintf(
				"{node_os=\"%s\",node_arch=\"%s\",platform_label=\"%s\"}",
				prometheusLabelEscaper.Replace(platform.OS), prometheusLabelEscaper.Replace(platform.Arch),
				prometheusLabelEscaper.Replace(platform.Label),
			)
		}

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_workers_by_platform gauge")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_workers_by_platform The number of connected workers by OS, arch, and platform label.")
		for i, platform := range platforms {
			fmt.Fprintf(&metrics, "jolt_scheduler_workers_by_platform%s %d\n", platformLabels[i], stats.WorkersByPlatform[platform].Workers)
		}

		fmt.Fprintln(&metrics, "# TYPE jolt_scheduler_workers_active_by_platform gauge")
		fmt.Fprintln(&metrics, "# HELP jolt_scheduler_workers_active_by_platform The number of connected workers unavailable for scheduling by OS, arch, and platform label, including workers awaiting acknowledgement.")
		for i, platform := range platforms {
			fmt.Fprintf(&metrics, "jolt_scheduler_workers_active_by_platform%s %d\n", platformLabels[i], stats.WorkersByPlatform[platform].ActiveWorkers)
		}

		w.Header().Set("Content-Type", "text/plain; charset=UTF-8")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(metrics.String()))
	})
}
