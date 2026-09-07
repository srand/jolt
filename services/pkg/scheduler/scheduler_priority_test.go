package scheduler

import (
	"context"
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
