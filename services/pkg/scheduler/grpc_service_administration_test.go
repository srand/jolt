package scheduler

import (
	"context"
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Lists the workers through the administration service, by id.
func listWorkers(t *testing.T, admin *adminService) map[string]*protocol.ListWorkersResponse_Worker {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	response, err := admin.ListWorkers(ctx, &protocol.ListWorkersRequest{})
	require.NoError(t, err)

	workers := map[string]*protocol.ListWorkersResponse_Worker{}
	for _, worker := range response.Workers {
		workers[worker.Id] = worker
	}
	return workers
}

func TestListWorkersShowsTheirTasks(t *testing.T) {
	scheduler := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	scheduler.AddObserver(hub)
	admin := NewAdminService(scheduler, hub)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go scheduler.Run(ctx)

	build := scheduler.NewBuild("build", &protocol.BuildRequest{Environment: &protocol.BuildEnvironment{}})
	defer build.Close()
	task := addTask(build, "task")

	platform := NewPlatformWithDefaults()
	platform.AddProperty("label", "test")
	worker, err := scheduler.NewWorker(platform, NewPlatform())
	require.NoError(t, err)
	defer worker.Close()

	observer, err := scheduler.ScheduleBuild(build)
	require.NoError(t, err)
	defer observer.Close()
	taskObserver, err := scheduler.ScheduleTask(build.Id(), task.Identity())
	require.NoError(t, err)
	defer taskObserver.Close()

	// The worker has claimed its executor, as when its executor stream
	// connects, and is running the task.
	require.NotNil(t, <-worker.Builds())
	executor, err := scheduler.NewExecutor(worker.Id(), build.Id())
	require.NoError(t, err)
	defer executor.Close()
	require.Equal(t, task, <-executor.Tasks())

	idle, err := scheduler.NewWorker(NewPlatformWithDefaults(), NewPlatform())
	require.NoError(t, err)
	defer idle.Close()

	workers := listWorkers(t, admin)
	require.Contains(t, workers, worker.Id())
	require.Contains(t, workers, idle.Id())
	assert.True(t, platform.Equals(NewPlatformFromProtobuf(workers[worker.Id()].Platform)))
	assert.Nil(t, workers[idle.Id()].Task, "idle worker has no task")
	if assert.NotNil(t, workers[worker.Id()].Task) {
		assert.Equal(t, task.Identity(), workers[worker.Id()].Task.Id)
		assert.Equal(t, "task", workers[worker.Id()].Task.Name)
		assert.Equal(t, protocol.TaskStatus_TASK_ASSIGNED, workers[worker.Id()].Task.Status)
	}

	task.PostStatusUpdate(protocol.TaskStatus_TASK_RUNNING)
	if task := listWorkers(t, admin)[worker.Id()].Task; assert.NotNil(t, task) {
		assert.Equal(t, protocol.TaskStatus_TASK_RUNNING, task.Status)
	}

	task.PostStatusUpdate(protocol.TaskStatus_TASK_PASSED)
	assert.Nil(t, listWorkers(t, admin)[worker.Id()].Task, "finished task is not listed")

	idle.Close()
	assert.Eventually(t, func() bool {
		_, listed := listWorkers(t, admin)[idle.Id()]
		return !listed
	}, 5*time.Second, 10*time.Millisecond, "removed worker is listed")
}

func TestListWorkersWithoutEventHub(t *testing.T) {
	hub := NewEventHub("http://logstash")
	ctx, cancel := context.WithCancel(context.Background())
	stopped := make(chan struct{})
	go func() {
		hub.Run(ctx)
		close(stopped)
	}()
	cancel()
	<-stopped

	admin := NewAdminService(NewPriorityScheduler(), hub)
	_, err := admin.ListWorkers(context.Background(), &protocol.ListWorkersRequest{})
	assert.Equal(t, codes.Unavailable, status.Code(err))

	// A request that is given up on ends with the status of its context
	hub = NewEventHub("http://logstash")
	ctx, cancel = context.WithCancel(context.Background())
	cancel()
	_, err = NewAdminService(NewPriorityScheduler(), hub).ListWorkers(ctx, &protocol.ListWorkersRequest{})
	assert.Equal(t, codes.Canceled, status.Code(err))
}
