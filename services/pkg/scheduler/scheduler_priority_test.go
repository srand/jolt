package scheduler

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
)

// Scheduling a task while an executor is idle must not deadlock the scheduler.
//
// The unicast queue delivers the task to the waiting executor from within
// priorityBuild.ScheduleTask, which holds the build's write lock. Taking the
// build lock again from the queue's Selected callback wedges the scheduler for
// good: the client waits for a task that is never dispatched.
func TestScheduleTaskWithIdleExecutor(t *testing.T) {
	scheduler := NewPriorityScheduler()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go scheduler.Run(ctx)

	request := protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{
			Tasks: map[string]*protocol.Task{},
		},
	}
	uid, _ := uuid.NewRandom()
	id, _ := utils.Sha1String(uid.String())
	build := scheduler.NewBuild(id, &request)

	taskA := addTask(build, "a")
	taskB := addTask(build, "b")

	worker, err := scheduler.NewWorker(NewPlatformWithDefaults(), NewPlatform())
	assert.NoError(t, err)

	observer, err := scheduler.ScheduleBuild(build)
	assert.NoError(t, err)
	defer observer.Close()

	observerA, err := scheduler.ScheduleTask(build.Id(), taskA.Identity())
	assert.NoError(t, err)
	defer observerA.Close()

	<-worker.Builds()

	executor, err := scheduler.NewExecutor(worker.Id(), build.Id())
	assert.NoError(t, err)
	assert.Equal(t, taskA, <-executor.Tasks())

	// The first task completes and its executor becomes available again.
	taskA.PostStatusUpdate(protocol.TaskStatus_TASK_PASSED)
	executor.Acknowledge()

	// The client now schedules the second task, which the queue hands straight
	// to the idle executor.
	scheduled := make(chan struct{})
	go func() {
		defer close(scheduled)
		observerB, err := scheduler.ScheduleTask(build.Id(), taskB.Identity())
		if err == nil {
			defer observerB.Close()
		}
	}()

	select {
	case <-scheduled:
	case <-time.After(30 * time.Second):
		t.Fatal("scheduler deadlocked while scheduling a task for an idle executor")
	}

	assert.Equal(t, taskB, <-executor.Tasks())
	assert.Equal(t, protocol.TaskStatus_TASK_ASSIGNED, taskB.Status())
}

func TestBuildPriorityOrder(t *testing.T) {
	now := time.Now()
	build := func(id string, priority int, scheduledAt time.Time) *priorityBuild {
		return &priorityBuild{mu: utils.NewRWMutex(), id: id, priority: priority, scheduledAt: scheduledAt}
	}
	high := build("high", 10, now)
	low := build("low", 0, now)
	older := build("older", 0, now.Add(-time.Second))
	twin := build("twin", 0, now)

	// Builds with higher priority come first, then the oldest
	assert.Equal(t, -1, buildPriorityFunc(high, low))
	assert.Equal(t, 1, buildPriorityFunc(low, high))
	assert.Equal(t, -1, buildPriorityFunc(older, low))
	assert.Equal(t, 1, buildPriorityFunc(low, older))
	assert.Equal(t, -1, buildPriorityFunc(high, older), "priority before age")
	assert.Equal(t, 0, buildPriorityFunc(low, twin))

	assert.True(t, buildEqualityFunc(low, low))
	assert.True(t, buildEqualityFunc(low, build("low", 5, now.Add(time.Hour))))
	assert.False(t, buildEqualityFunc(low, twin))
	assert.False(t, buildEqualityFunc(twin, low))
}

// A free worker must go to the oldest build it can serve, even when the
// oldest ready builds have no task for it.
func TestWorkerGoesToOldestCompatibleBuild(t *testing.T) {
	scheduler := NewPriorityScheduler()
	start := time.Now()

	builds := make([]*priorityBuild, 8)
	for i := range builds {
		builds[i] = scheduler.NewBuild(fmt.Sprint("build", i), &protocol.BuildRequest{Environment: &protocol.BuildEnvironment{}}).(*priorityBuild)
		builds[i].scheduledAt = start.Add(time.Duration(i) * time.Second)
		defer builds[i].Close()
	}

	// Enqueue newest first, so that the heap's array isn't in priority order
	for i := len(builds) - 1; i >= 0; i-- {
		properties := []string{}
		if i < 3 {
			properties = append(properties, "label=other")
		}
		task := addTask(builds[i], "task", properties...)
		observer, err := scheduler.ScheduleBuild(builds[i])
		assert.NoError(t, err)
		defer observer.Close()
		taskObserver, err := scheduler.ScheduleTask(builds[i].Id(), task.Identity())
		assert.NoError(t, err)
		defer taskObserver.Close()
	}

	worker, err := scheduler.NewWorker(NewPlatformWithDefaults(), NewPlatform())
	assert.NoError(t, err)
	defer worker.Close()

	scheduler.selectTaskAndWorker()
	assert.Equal(t, builds[3].Id(), (<-worker.Builds()).Id())
}

func TestTaskSelection(t *testing.T) {
	scheduler := NewPriorityScheduler()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go scheduler.Run(ctx)

	newWorker := func(properties, taskProperties []string) Worker {
		platform := NewPlatform()
		for _, property := range properties {
			key, value, _ := strings.Cut(property, "=")
			platform.AddProperty(key, value)
		}
		taskPlatform := NewPlatform()
		for _, property := range taskProperties {
			key, value, _ := strings.Cut(property, "=")
			taskPlatform.AddProperty(key, value)
		}
		worker, err := scheduler.NewWorker(platform, taskPlatform)
		assert.NoError(t, err)
		t.Cleanup(func() { worker.Close() })
		return worker
	}

	build := scheduler.NewBuild("build", &protocol.BuildRequest{Environment: &protocol.BuildEnvironment{}})
	task := addTask(build, "task", "label=fast", "tag=gpu")
	callbacks := &priorityUnicastCallbacks{}

	for name, test := range map[string]struct {
		worker Worker
		want   bool
	}{
		"fulfills task":              {newWorker([]string{"label=fast", "tag=gpu", "node.os=linux"}, nil), true},
		"missing property":           {newWorker([]string{"label=fast"}, nil), false},
		"task fulfills worker":       {newWorker([]string{"label=fast", "tag=gpu"}, []string{"tag=gpu"}), true},
		"task doesn't fulfill":       {newWorker([]string{"label=fast", "tag=gpu"}, []string{"tag=cpu"}), false},
		"neither fulfills the other": {newWorker([]string{"label=slow"}, []string{"tag=cpu"}), false},
	} {
		assert.Equal(t, test.want, callbacks.Select(task, test.worker), name)
	}

	worker := newWorker([]string{"label=fast", "tag=gpu"}, nil)
	task.AssignToWorker(worker)
	assert.False(t, callbacks.Select(task, worker), "assigned task")
	task.AssignToWorker(nil)
	assert.True(t, callbacks.Select(task, worker))

	task.status = protocol.TaskStatus_TASK_PASSED
	assert.False(t, callbacks.Select(task, worker), "completed task")
}

func TestTaskStatisticsByStatus(t *testing.T) {
	for status, want := range map[protocol.TaskStatus][2]int64{
		protocol.TaskStatus_TASK_FAILED:     {1, 0},
		protocol.TaskStatus_TASK_ERROR:      {1, 0},
		protocol.TaskStatus_TASK_UNSTABLE:   {1, 0},
		protocol.TaskStatus_TASK_PASSED:     {0, 1},
		protocol.TaskStatus_TASK_SKIPPED:    {0, 1},
		protocol.TaskStatus_TASK_UPLOADED:   {0, 1},
		protocol.TaskStatus_TASK_DOWNLOADED: {0, 1},
		protocol.TaskStatus_TASK_RUNNING:    {0, 0},
		protocol.TaskStatus_TASK_CANCELLED:  {0, 0},
	} {
		scheduler := NewPriorityScheduler()
		build := scheduler.NewBuild("build", &protocol.BuildRequest{Environment: &protocol.BuildEnvironment{}})
		task := addTask(build, "task")

		scheduler.TaskStatusChanged(task, status)
		stats := scheduler.Statistics()
		assert.Equal(t, want[0], stats.FailedTasks, status.String())
		assert.Equal(t, want[1], stats.SuccessfulTasks, status.String())
		assert.Equal(t, want[0]+want[1], stats.CompletedTasks, status.String())
	}
}

func TestListBuilds(t *testing.T) {
	scheduler := NewPriorityScheduler()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go scheduler.Run(ctx)

	build := scheduler.NewBuild("build", &protocol.BuildRequest{Environment: &protocol.BuildEnvironment{}})
	taskA := addTask(build, "a")
	taskB := addTask(build, "b")

	worker, err := scheduler.NewWorker(NewPlatformWithDefaults(), NewPlatform())
	assert.NoError(t, err)
	defer worker.Close()

	observer, err := scheduler.ScheduleBuild(build)
	assert.NoError(t, err)
	defer observer.Close()
	observerA, err := scheduler.ScheduleTask(build.Id(), taskA.Identity())
	assert.NoError(t, err)
	defer observerA.Close()

	<-worker.Builds()
	executor, err := scheduler.NewExecutor(worker.Id(), build.Id())
	assert.NoError(t, err)
	defer executor.Close()
	assert.Equal(t, taskA, <-executor.Tasks())

	builds := scheduler.ListBuilds(false)
	if assert.Len(t, builds.Builds, 1) {
		assert.Equal(t, "build", builds.Builds[0].Id)
		assert.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, builds.Builds[0].Status)
		assert.Empty(t, builds.Builds[0].Tasks)
	}

	builds = scheduler.ListBuilds(true)
	if assert.Len(t, builds.Builds, 1) {
		names := map[string]protocol.TaskStatus{}
		for _, task := range builds.Builds[0].Tasks {
			names[task.Name] = task.Status
		}
		assert.Equal(t, map[string]protocol.TaskStatus{
			"a": protocol.TaskStatus_TASK_ASSIGNED,
			"b": taskB.Status(),
		}, names)
	}
}
