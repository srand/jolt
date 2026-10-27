package scheduler

import (
	"context"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// A task that is assigned to an already idle worker the instant it is queued
// must still be reported as assigned on the event stream.
func TestEventHubAssignedAtWhenAssignedWhileScheduling(t *testing.T) {
	scheduler := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	scheduler.AddObserver(hub)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go scheduler.Run(ctx)

	build := scheduler.NewBuild("build", &protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{Tasks: map[string]*protocol.Task{}},
	})
	defer build.Close()

	task1 := addTask(build, "task1")
	task2 := addTask(build, "task2")

	worker, err := scheduler.NewWorker(NewPlatformWithDefaults(), NewPlatform())
	require.NoError(t, err)
	defer worker.Close()

	buildObserver, err := scheduler.ScheduleBuild(build)
	require.NoError(t, err)
	defer buildObserver.Close()

	// The first task is assigned by the scheduler goroutine, after the task's
	// observer hooks have been installed.
	taskObserver1, err := scheduler.ScheduleTask(build.Id(), task1.Identity())
	require.NoError(t, err)
	defer taskObserver1.Close()

	require.NotNil(t, <-worker.Builds())
	executor, err := scheduler.NewExecutor(worker.Id(), build.Id())
	require.NoError(t, err)
	defer executor.Close()
	require.Equal(t, task1, <-executor.Tasks())

	// Release the worker's queue consumer so that it is idle and waiting.
	executor.Acknowledge()

	// The second task is handed to the idle consumer synchronously, from within
	// ScheduleTask itself.
	taskObserver2, err := scheduler.ScheduleTask(build.Id(), task2.Identity())
	require.NoError(t, err)
	defer taskObserver2.Close()

	require.Equal(t, task2, <-executor.Tasks())
	require.Equal(t, protocol.TaskStatus_TASK_ASSIGNED, task2.Status())

	consumer, err := hub.Subscribe(context.Background(), &EventFilter{Tasks: true})
	require.NoError(t, err)

	snapshot := recv(t, consumer).GetSnapshot()
	require.NotNil(t, snapshot)
	require.Len(t, snapshot.Tasks, 2)

	var info *protocol.TaskInfo
	for _, task := range snapshot.Tasks {
		assert.Equal(t, build.Id(), task.BuildId)
		if task.Instance == task2.Instance() {
			info = task
		}
	}
	require.NotNil(t, info, "task2 must be present in the snapshot")

	assert.Equal(t, protocol.TaskStatus_TASK_ASSIGNED, info.Status)
	assert.NotNil(t, info.AssignedAt, "assigned_at must be set for an assigned task")
}
