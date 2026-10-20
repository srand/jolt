package scheduler

import (
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWorkerStatisticsByPlatform(t *testing.T) {
	scheduler := NewPriorityScheduler()
	assert.Zero(t, scheduler.Statistics().Workers)
	assert.Empty(t, scheduler.Statistics().WorkersByPlatform)

	newWorker := func(os, arch, hostname, label, pool string) Worker {
		platform := NewPlatform()
		platform.AddProperty("node.os", os)
		platform.AddProperty("node.arch", arch)
		platform.AddProperty("worker.hostname", hostname)
		platform.AddProperty("node.id", hostname)
		platform.AddProperty("label", label)
		platform.AddProperty("pool", pool)
		worker, err := scheduler.NewWorker(platform, NewPlatform())
		require.NoError(t, err)
		t.Cleanup(worker.Close)
		return worker
	}

	active := newWorker("linux", "amd64", "worker-1", "tiny", "active")
	idle := newWorker("linux", "amd64", "worker-2", "tiny", "idle")
	arm := newWorker("linux", "arm64", "worker-3", "tiny", "idle")
	signing := newWorker("linux", "amd64", "worker-4", "signing", "idle")
	unknown, err := scheduler.NewWorker(NewPlatform(), NewPlatform())
	require.NoError(t, err)
	t.Cleanup(unknown.Close)

	amd64Platform := WorkerPlatform{OS: "linux", Arch: "amd64", Label: "tiny"}
	arm64Platform := WorkerPlatform{OS: "linux", Arch: "arm64", Label: "tiny"}
	signingPlatform := WorkerPlatform{OS: "linux", Arch: "amd64", Label: "signing"}
	unknownPlatform := WorkerPlatform{OS: "unknown", Arch: "unknown", Label: "unknown"}
	expected := map[WorkerPlatform]WorkerStatistics{
		amd64Platform:   {Workers: 2},
		arm64Platform:   {Workers: 1},
		signingPlatform: {Workers: 1},
		unknownPlatform: {Workers: 1},
	}
	check := func(workers int64) {
		t.Helper()
		stats := scheduler.Statistics()
		assert.Equal(t, workers, stats.Workers)
		assert.Equal(t, expected, stats.WorkersByPlatform)
		var total, available int64
		for _, counts := range stats.WorkersByPlatform {
			assert.GreaterOrEqual(t, counts.ActiveWorkers, int64(0))
			assert.LessOrEqual(t, counts.ActiveWorkers, counts.Workers)
			available += counts.Workers - counts.ActiveWorkers
			total += counts.Workers
		}
		assert.Equal(t, stats.Workers, total)
		// Consumers can recover availability by subtracting active from total.
		scheduler.RLock()
		assert.Equal(t, int64(len(scheduler.availWorkers)), available)
		scheduler.RUnlock()
	}
	check(5)
	snapshot := scheduler.Statistics()

	build := scheduler.NewBuild("build", &protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{Tasks: map[string]*protocol.Task{}},
	})
	t.Cleanup(build.Close)
	task := addTask(build, "task", "node.os=linux", "node.arch=amd64", "label=tiny", "pool=active")
	task2 := addTask(build, "task2", "node.os=linux", "node.arch=amd64", "label=tiny", "pool=active")
	observer, err := scheduler.ScheduleBuild(build)
	require.NoError(t, err)
	t.Cleanup(observer.Close)
	taskObserver, err := scheduler.ScheduleTask(build.Id(), task.Identity())
	require.NoError(t, err)
	t.Cleanup(taskObserver.Close)

	// Run scheduling synchronously so each statistics snapshot observes a known state.
	scheduler.selectTaskAndWorker()
	expected[amd64Platform] = WorkerStatistics{Workers: 2, ActiveWorkers: 1}
	check(5)
	assert.Equal(t, WorkerStatistics{Workers: 2}, snapshot.WorkersByPlatform[amd64Platform])
	require.Equal(t, build, <-active.Builds())

	executor, err := scheduler.NewExecutor(active.Id(), build.Id())
	require.NoError(t, err)
	t.Cleanup(executor.Close)
	// Enlisting removes the pending executor association, but the worker stays active.
	check(5)
	select {
	case scheduledTask := <-executor.Tasks():
		require.Equal(t, task, scheduledTask)
	case <-time.After(time.Second):
		t.Fatal("task was not delivered to executor")
	}
	executor.Acknowledge()
	executor.Close()
	check(5)
	active.Acknowledge()
	expected[amd64Platform] = WorkerStatistics{Workers: 2}
	check(5)

	// Disconnecting an active worker removes it from both its platform and total counts.
	taskObserver2, err := scheduler.ScheduleTask(build.Id(), task2.Identity())
	require.NoError(t, err)
	t.Cleanup(taskObserver2.Close)
	scheduler.selectTaskAndWorker()
	expected[amd64Platform] = WorkerStatistics{Workers: 2, ActiveWorkers: 1}
	check(5)
	active.Close()
	expected[amd64Platform] = WorkerStatistics{Workers: 1}
	check(4)
	idle.Close()
	delete(expected, amd64Platform)
	check(3)
	arm.Close()
	delete(expected, arm64Platform)
	check(2)
	signing.Close()
	delete(expected, signingPlatform)
	check(1)
	unknown.Close()
	delete(expected, unknownPlatform)
	check(0)
}

func TestWorkerStatisticsPlatformProperties(t *testing.T) {
	for _, test := range []struct {
		name     string
		os       []string
		arch     []string
		labels   []string
		expected WorkerPlatform
	}{
		{"missing", nil, nil, nil, WorkerPlatform{OS: "unknown", Arch: "unknown", Label: "unknown"}},
		{"empty", []string{""}, []string{""}, []string{""}, WorkerPlatform{OS: "unknown", Arch: "unknown", Label: "unknown"}},
		{"partial", []string{"linux"}, nil, nil, WorkerPlatform{OS: "linux", Arch: "unknown", Label: "unknown"}},
		{"unlabeled", []string{"linux"}, []string{"amd64"}, nil, WorkerPlatform{OS: "linux", Arch: "amd64", Label: "unknown"}},
		{"label-only", nil, nil, []string{"tiny"}, WorkerPlatform{OS: "unknown", Arch: "unknown", Label: "tiny"}},
		{"duplicate", []string{"linux", "linux"}, []string{"amd64", "amd64"}, []string{"tiny", "tiny"}, WorkerPlatform{OS: "linux", Arch: "amd64", Label: "tiny"}},
		{"multiple", []string{"windows", "linux"}, []string{"arm64", "amd64"}, []string{"tiny", "signing"}, WorkerPlatform{OS: "multiple", Arch: "multiple", Label: "signing,tiny"}},
		{"multiple-labels", []string{"linux"}, []string{"amd64"}, []string{"tiny", "signing"}, WorkerPlatform{OS: "linux", Arch: "amd64", Label: "signing,tiny"}},
		{"reversed-labels", []string{"linux"}, []string{"amd64"}, []string{"signing", "tiny"}, WorkerPlatform{OS: "linux", Arch: "amd64", Label: "signing,tiny"}},
		{"three-labels", []string{"linux"}, []string{"amd64"}, []string{"toolsctrl", "tiny", "signing"}, WorkerPlatform{OS: "linux", Arch: "amd64", Label: "signing,tiny,toolsctrl"}},
		{"empty-with-labels", []string{"linux"}, []string{"amd64"}, []string{"tiny", "", "signing"}, WorkerPlatform{OS: "linux", Arch: "amd64", Label: "signing,tiny"}},
	} {
		t.Run(test.name, func(t *testing.T) {
			scheduler := NewPriorityScheduler()
			platform := NewPlatform()
			for _, value := range test.os {
				platform.AddProperty("node.os", value)
			}
			for _, value := range test.arch {
				platform.AddProperty("node.arch", value)
			}
			for _, value := range test.labels {
				platform.AddProperty("label", value)
			}
			taskPlatform := NewPlatform()
			taskPlatform.AddProperty("node.os", "task-os")
			taskPlatform.AddProperty("node.arch", "task-arch")
			taskPlatform.AddProperty("label", "task-label")
			worker, err := scheduler.NewWorker(platform, taskPlatform)
			require.NoError(t, err)
			t.Cleanup(worker.Close)
			for range 10 {
				assert.Equal(t, map[WorkerPlatform]WorkerStatistics{
					test.expected: {Workers: 1},
				}, scheduler.Statistics().WorkersByPlatform)
			}
		})
	}
}
