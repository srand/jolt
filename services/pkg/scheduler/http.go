package scheduler

import (
	"fmt"
	"net/http"
	"slices"
	"strings"

	"github.com/labstack/echo/v4"
)

var prometheusLabelEscaper = strings.NewReplacer("\\", "\\\\", "\"", "\\\"", "\n", "\\n")

func NewHttpHandler(scheduler Scheduler, r *echo.Echo) {
	r.GET("/metrics", func(c echo.Context) error {
		stats := scheduler.Statistics()

		metrics := fmt.Sprintln("# TYPE jolt_scheduler_builds gauge")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_builds The total number of builds currently running.")
		metrics += fmt.Sprintf("jolt_scheduler_builds %d\n", stats.Builds)

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_builds_total counter")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_builds_total The total number of completed builds.")
		metrics += fmt.Sprintf("jolt_scheduler_builds_total %d\n", stats.CompletedBuilds)

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_tasks_queued gauge")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_tasks_queued The total number of tasks currently queued.")
		metrics += fmt.Sprintf("jolt_scheduler_tasks_queued %d\n", stats.QueuedTasks)

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_tasks_running gauge")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_tasks_running The total number of tasks currently running.")
		metrics += fmt.Sprintf("jolt_scheduler_tasks_running %d\n", stats.RunningTasks)

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_tasks_failed_total counter")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_tasks_failed_total The total number of failed tasks.")
		metrics += fmt.Sprintf("jolt_scheduler_tasks_failed_total %d\n", stats.FailedTasks)

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_tasks_passed_total counter")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_tasks_passed_total The total number of successful tasks.")
		metrics += fmt.Sprintf("jolt_scheduler_tasks_passed_total %d\n", stats.SuccessfulTasks)

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_tasks_total counter")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_tasks_total The total number of completed tasks.")
		metrics += fmt.Sprintf("jolt_scheduler_tasks_total %d\n", stats.CompletedTasks)

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_workers gauge")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_workers The total number of workers currently connected.")
		metrics += fmt.Sprintf("jolt_scheduler_workers %d\n", stats.Workers)

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

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_workers_by_platform gauge")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_workers_by_platform The number of connected workers by OS, arch, and platform label.")
		for _, platform := range platforms {
			metrics += fmt.Sprintf(
				"jolt_scheduler_workers_by_platform{node_os=\"%s\",node_arch=\"%s\",platform_label=\"%s\"} %d\n",
				prometheusLabelEscaper.Replace(platform.OS), prometheusLabelEscaper.Replace(platform.Arch),
				prometheusLabelEscaper.Replace(platform.Label), stats.WorkersByPlatform[platform].Workers,
			)
		}

		metrics += fmt.Sprintln("# TYPE jolt_scheduler_workers_active_by_platform gauge")
		metrics += fmt.Sprintln("# HELP jolt_scheduler_workers_active_by_platform The number of connected workers unavailable for scheduling by OS, arch, and platform label, including workers awaiting acknowledgement.")
		for _, platform := range platforms {
			metrics += fmt.Sprintf(
				"jolt_scheduler_workers_active_by_platform{node_os=\"%s\",node_arch=\"%s\",platform_label=\"%s\"} %d\n",
				prometheusLabelEscaper.Replace(platform.OS), prometheusLabelEscaper.Replace(platform.Arch),
				prometheusLabelEscaper.Replace(platform.Label), stats.WorkersByPlatform[platform].ActiveWorkers,
			)
		}

		return c.String(http.StatusOK, metrics)
	})
}
