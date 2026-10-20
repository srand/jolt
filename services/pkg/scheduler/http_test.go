package scheduler

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/labstack/echo/v4"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type metricsScheduler struct {
	Scheduler
	stats *SchedulerStatistics
}

func (s metricsScheduler) Statistics() *SchedulerStatistics {
	return s.stats
}

func TestWorkerMetrics(t *testing.T) {
	stats := &SchedulerStatistics{
		Workers: 5,
		WorkersByPlatform: map[WorkerPlatform]WorkerStatistics{
			{OS: "linux", Arch: "arm64"}:                                             {Workers: 1},
			{OS: "linux", Arch: "amd64", Label: "tiny"}:                              {Workers: 2, ActiveWorkers: 1},
			{OS: "linux", Arch: "amd64", Label: "signing"}:                           {Workers: 1, ActiveWorkers: 1},
			{OS: "custom\\os\"\n", Arch: "custom\tarch", Label: "custom\\label\"\n"}: {Workers: 1, ActiveWorkers: 1},
		},
	}
	router := echo.New()
	NewHttpHandler(metricsScheduler{stats: stats}, router)

	for range 5 {
		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
		assert.Equal(t, http.StatusOK, response.Code)
		assert.Equal(t, echo.MIMETextPlainCharsetUTF8, response.Header().Get("Content-Type"))
		body := response.Body.String()
		assert.NotContains(t, body, "jolt_scheduler_workers_available_by_platform")
		assert.Contains(t, body, "# TYPE jolt_scheduler_workers gauge\n")
		assert.Contains(t, body, "# HELP jolt_scheduler_workers The total number of workers currently connected.\n")
		assert.Contains(t, body, "# HELP jolt_scheduler_workers_active_by_platform The number of connected workers unavailable for scheduling by OS, arch, and platform label, including workers awaiting acknowledgement.\n")
		assert.Contains(t, body, "\njolt_scheduler_workers 5\n")

		for _, test := range []struct {
			name   string
			counts [4]int
		}{
			{"jolt_scheduler_workers_by_platform", [4]int{1, 1, 2, 1}},
			{"jolt_scheduler_workers_active_by_platform", [4]int{1, 1, 1, 0}},
		} {
			assert.Contains(t, body, fmt.Sprintf("# TYPE %s gauge\n# HELP %s ", test.name, test.name))
			// Samples are sorted by OS, architecture and Jolt label, and values only
			// escape the backslashes, quotes and newlines required by Prometheus.
			expected := fmt.Sprintf("%s{node_os=\"custom\\\\os\\\"\\n\",node_arch=\"custom\tarch\",platform_label=\"custom\\\\label\\\"\\n\"} %d\n", test.name, test.counts[0])
			expected += fmt.Sprintf("%s{node_os=\"linux\",node_arch=\"amd64\",platform_label=\"signing\"} %d\n", test.name, test.counts[1])
			expected += fmt.Sprintf("%s{node_os=\"linux\",node_arch=\"amd64\",platform_label=\"tiny\"} %d\n", test.name, test.counts[2])
			expected += fmt.Sprintf("%s{node_os=\"linux\",node_arch=\"arm64\",platform_label=\"\"} %d\n", test.name, test.counts[3])
			assert.Contains(t, body, expected)
			assert.Equal(t, 4, strings.Count(body, test.name+"{"))
		}
	}
}

func TestWorkerMetricsWithMultipleLabels(t *testing.T) {
	scheduler := NewPriorityScheduler()
	for _, labels := range [][]string{
		{"tiny", "signing"},
		{"signing", "tiny"},
		{"toolsctrl", "tiny"},
	} {
		platform := NewPlatform()
		platform.AddProperty("node.os", "linux")
		platform.AddProperty("node.arch", "amd64")
		for _, label := range labels {
			platform.AddProperty("label", label)
		}
		worker, err := scheduler.NewWorker(platform, NewPlatform())
		require.NoError(t, err)
		t.Cleanup(worker.Close)
	}
	assert.Equal(t, map[WorkerPlatform]WorkerStatistics{
		{OS: "linux", Arch: "amd64", Label: "signing,tiny"}:   {Workers: 2},
		{OS: "linux", Arch: "amd64", Label: "tiny,toolsctrl"}: {Workers: 1},
	}, scheduler.Statistics().WorkersByPlatform)
	router := echo.New()
	NewHttpHandler(scheduler, router)
	for range 10 {
		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
		assert.Equal(t, http.StatusOK, response.Code)
		body := response.Body.String()
		assert.NotContains(t, body, "jolt_scheduler_workers_available_by_platform")
		assert.Contains(t, body, "\njolt_scheduler_workers 3\n")
		for _, test := range []struct {
			name   string
			counts [2]int
		}{
			{"jolt_scheduler_workers_by_platform", [2]int{2, 1}},
			{"jolt_scheduler_workers_active_by_platform", [2]int{0, 0}},
		} {
			assert.Contains(t, body, fmt.Sprintf("%s{node_os=\"linux\",node_arch=\"amd64\",platform_label=\"signing,tiny\"} %d\n", test.name, test.counts[0]))
			assert.Contains(t, body, fmt.Sprintf("%s{node_os=\"linux\",node_arch=\"amd64\",platform_label=\"tiny,toolsctrl\"} %d\n", test.name, test.counts[1]))
			assert.Equal(t, 2, strings.Count(body, test.name+"{"))
		}
	}
}

func TestWorkerMetricsWithoutWorkers(t *testing.T) {
	router := echo.New()
	NewHttpHandler(NewPriorityScheduler(), router)
	response := httptest.NewRecorder()
	router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	assert.Equal(t, http.StatusOK, response.Code)
	body := response.Body.String()
	assert.NotContains(t, body, "jolt_scheduler_workers_available_by_platform")
	assert.Contains(t, body, "\njolt_scheduler_workers 0\n")
	for _, name := range []string{
		"jolt_scheduler_workers_by_platform",
		"jolt_scheduler_workers_active_by_platform",
	} {
		assert.Contains(t, body, fmt.Sprintf("# TYPE %s gauge\n# HELP %s ", name, name))
		assert.NotContains(t, body, name+"{")
	}
}
