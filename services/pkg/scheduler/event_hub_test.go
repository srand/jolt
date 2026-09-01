package scheduler

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestHub(t *testing.T) (*EventHub, context.CancelFunc) {
	hub := NewEventHub("http://logstash")
	ctx, cancel := context.WithCancel(context.Background())
	go hub.Run(ctx)
	t.Cleanup(cancel)
	return hub, cancel
}

func newTestTask(t *testing.T, name string, properties ...string) *Task {
	build := &priorityBuild{
		id:             "build",
		tasks:          map[string]*Task{},
		buildObservers: NewBuildUpdateObservers(),
	}
	return addTask(build, name, properties...)
}

// Applies an update and waits for the hub to have processed it.
func postSync(t *testing.T, hub *EventHub, post func()) {
	post()

	// The hub processes updates in order, so a completed subscription
	// implies all previously posted updates have been applied.
	_, err := hub.Subscribe(context.Background(), &EventFilter{NoSnapshot: true})
	require.NoError(t, err)
}

func recv(t *testing.T, consumer *utils.BroadcastConsumer[*protocol.SchedulerEvent]) *protocol.SchedulerEvent {
	t.Helper()
	select {
	case event, ok := <-consumer.Chan:
		require.True(t, ok, "consumer channel was closed")
		return event
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for event")
		return nil
	}
}

func TestEventHubSnapshotHasQueuedAndRunningTasks(t *testing.T) {
	hub, _ := newTestHub(t)

	queued := newTestTask(t, "queued")
	running := newTestTask(t, "running")
	done := newTestTask(t, "done")

	postSync(t, hub, func() {
		hub.TaskScheduled(queued)
		hub.TaskScheduled(running)
		hub.TaskStatusChanged(running, protocol.TaskStatus_TASK_RUNNING)
		hub.TaskScheduled(done)
		hub.TaskStatusChanged(done, protocol.TaskStatus_TASK_PASSED)
	})

	consumer, err := hub.Subscribe(context.Background(), &EventFilter{Tasks: true, Workers: true})
	require.NoError(t, err)

	snapshot := recv(t, consumer).GetSnapshot()
	require.NotNil(t, snapshot)

	statuses := map[string]protocol.TaskStatus{}
	for _, task := range snapshot.Tasks {
		statuses[task.Name] = task.Status
	}

	assert.Len(t, snapshot.Tasks, 2, "completed tasks must not be included")
	assert.Equal(t, protocol.TaskStatus_TASK_QUEUED, statuses["queued"])
	assert.Equal(t, protocol.TaskStatus_TASK_RUNNING, statuses["running"])
}

func TestEventHubSnapshotHasWorkers(t *testing.T) {
	hub, _ := newTestHub(t)

	platform := NewPlatform()
	platform.AddProperty("worker.hostname", "builder1")
	platform.AddProperty("label", "fast")

	id, _ := uuid.NewRandom()
	worker := &priorityWorker{id: id, platform: platform, taskPlatform: NewPlatform()}

	other, _ := uuid.NewRandom()
	gone := &priorityWorker{id: other, platform: NewPlatformWithDefaults(), taskPlatform: NewPlatform()}

	postSync(t, hub, func() {
		hub.WorkerEnlisted(worker)
		hub.WorkerEnlisted(gone)
		hub.WorkerDelisted(gone)
	})

	consumer, err := hub.Subscribe(context.Background(), nil)
	require.NoError(t, err)

	snapshot := recv(t, consumer).GetSnapshot()
	require.NotNil(t, snapshot)
	require.Len(t, snapshot.Workers, 1, "delisted workers must not be included")
	assert.Equal(t, worker.Id(), snapshot.Workers[0].Id)
	assert.Equal(t, "builder1", snapshot.Workers[0].Hostname)
}

func TestEventHubStreamsUpdatesAfterSnapshot(t *testing.T) {
	hub, _ := newTestHub(t)

	task := newTestTask(t, "task")
	postSync(t, hub, func() { hub.TaskScheduled(task) })

	consumer, err := hub.Subscribe(context.Background(), nil)
	require.NoError(t, err)

	snapshot := recv(t, consumer).GetSnapshot()
	require.Len(t, snapshot.Tasks, 1)
	assert.Equal(t, protocol.TaskStatus_TASK_QUEUED, snapshot.Tasks[0].Status)

	hub.TaskStatusChanged(task, protocol.TaskStatus_TASK_RUNNING)
	hub.TaskStatusChanged(task, protocol.TaskStatus_TASK_PASSED)

	running := recv(t, consumer).GetTask()
	require.NotNil(t, running)
	assert.Equal(t, protocol.TaskStatus_TASK_RUNNING, running.Status)
	assert.NotNil(t, running.StartedAt)

	passed := recv(t, consumer).GetTask()
	require.NotNil(t, passed)
	assert.Equal(t, protocol.TaskStatus_TASK_PASSED, passed.Status)
	assert.NotNil(t, passed.EndedAt)

	// Timestamps recorded on the first transition must be carried forward so
	// that they survive a subscriber restart.
	assert.Equal(t, snapshot.Tasks[0].QueuedAt.AsTime(), passed.QueuedAt.AsTime())
	assert.Equal(t, running.StartedAt.AsTime(), passed.StartedAt.AsTime())
}

func TestEventHubNoUpdateIsLostAcrossSnapshot(t *testing.T) {
	hub, _ := newTestHub(t)

	tasks := make([]*Task, 32)
	for i := range tasks {
		tasks[i] = newTestTask(t, "task")
		hub.TaskScheduled(tasks[i])
	}

	consumer, err := hub.Subscribe(context.Background(), nil)
	require.NoError(t, err)

	for _, task := range tasks {
		hub.TaskStatusChanged(task, protocol.TaskStatus_TASK_PASSED)
	}

	seen := map[string]protocol.TaskStatus{}
	for _, task := range recv(t, consumer).GetSnapshot().Tasks {
		seen[task.Instance] = task.Status
	}

	for range tasks {
		event := recv(t, consumer).GetTask()
		require.NotNil(t, event)
		previous, ok := seen[event.Instance]
		require.True(t, ok, "received an update for a task missing from the snapshot")
		require.NotEqual(t, previous, event.Status, "received a duplicate update")
		seen[event.Instance] = event.Status
	}

	assert.Len(t, seen, len(tasks))
	for _, status := range seen {
		assert.Equal(t, protocol.TaskStatus_TASK_PASSED, status)
	}
}

func TestEventHubAssociatesTaskWithWorker(t *testing.T) {
	hub, _ := newTestHub(t)

	platform := NewPlatform()
	platform.AddProperty("worker.hostname", "builder1")
	id, _ := uuid.NewRandom()
	worker := &priorityWorker{id: id, platform: platform, taskPlatform: NewPlatform()}

	task := newTestTask(t, "task")
	task.AssignToWorker(worker)
	task.SetMatchedPlatform(platform)

	postSync(t, hub, func() { hub.WorkerEnlisted(worker) })

	consumer, err := hub.Subscribe(context.Background(), nil)
	require.NoError(t, err)
	require.NotNil(t, recv(t, consumer).GetSnapshot())

	hub.TaskStatusChanged(task, protocol.TaskStatus_TASK_RUNNING)

	update := recv(t, consumer).GetTask()
	require.NotNil(t, update)
	assert.Equal(t, worker.Id(), update.WorkerId)
	assert.Equal(t, "builder1", update.WorkerHostname)

	assigned := recv(t, consumer).GetWorker()
	require.NotNil(t, assigned)
	assert.Equal(t, task.Instance(), assigned.Task.GetInstance())

	hub.TaskStatusChanged(task, protocol.TaskStatus_TASK_PASSED)
	require.NotNil(t, recv(t, consumer).GetTask())

	released := recv(t, consumer).GetWorker()
	require.NotNil(t, released)
	assert.Nil(t, released.Task, "worker must be released when its task completes")
}

func TestEventHubFilters(t *testing.T) {
	hub, _ := newTestHub(t)

	fast := newTestTask(t, "fast", "label=fast")
	slow := newTestTask(t, "slow", "label=slow")

	postSync(t, hub, func() {
		hub.TaskScheduled(fast)
		hub.TaskScheduled(slow)
		hub.TaskStatusChanged(slow, protocol.TaskStatus_TASK_RUNNING)
	})

	byLabel, err := hub.Subscribe(context.Background(), &EventFilter{Tasks: true, Labels: []string{"fast"}})
	require.NoError(t, err)
	snapshot := recv(t, byLabel).GetSnapshot()
	require.Len(t, snapshot.Tasks, 1)
	assert.Equal(t, "fast", snapshot.Tasks[0].Name)

	byStatus, err := hub.Subscribe(context.Background(), &EventFilter{
		Tasks:      true,
		TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_RUNNING},
	})
	require.NoError(t, err)
	snapshot = recv(t, byStatus).GetSnapshot()
	require.Len(t, snapshot.Tasks, 1)
	assert.Equal(t, "slow", snapshot.Tasks[0].Name)

	workersOnly, err := hub.Subscribe(context.Background(), &EventFilter{Workers: true})
	require.NoError(t, err)
	snapshot = recv(t, workersOnly).GetSnapshot()
	assert.Empty(t, snapshot.Tasks)
}

func TestEventHubReleasesWorkerOnRequeue(t *testing.T) {
	hub, _ := newTestHub(t)

	platform := NewPlatform()
	platform.AddProperty("worker.hostname", "builder1")
	id, _ := uuid.NewRandom()
	worker := &priorityWorker{id: id, platform: platform, taskPlatform: NewPlatform()}

	task := newTestTask(t, "task")
	task.AssignToWorker(worker)
	task.SetMatchedPlatform(platform)

	postSync(t, hub, func() {
		hub.WorkerEnlisted(worker)
		hub.TaskStatusChanged(task, protocol.TaskStatus_TASK_RUNNING)
	})

	consumer, err := hub.Subscribe(context.Background(), nil)
	require.NoError(t, err)
	require.NotNil(t, recv(t, consumer).GetSnapshot())

	// The scheduler unassigns the task before returning it to the queue.
	task.AssignToWorker(nil)
	hub.TaskStatusChanged(task, protocol.TaskStatus_TASK_QUEUED)

	requeued := recv(t, consumer).GetTask()
	require.NotNil(t, requeued)
	assert.Empty(t, requeued.WorkerId, "a queued task must not be attributed to a worker")
	assert.Empty(t, requeued.WorkerHostname)
	assert.Nil(t, requeued.StartedAt)

	released := recv(t, consumer).GetWorker()
	require.NotNil(t, released)
	assert.Nil(t, released.Task, "worker must be released when its task is requeued")
}

func TestEventFilterDefaultsToEverything(t *testing.T) {
	filter := NewEventFilter(&protocol.StreamEventsRequest{})
	assert.True(t, filter.Tasks)
	assert.True(t, filter.Workers)
	assert.True(t, filter.MatchTask(&protocol.TaskInfo{}))
	assert.True(t, filter.MatchWorker(&protocol.WorkerInfo{}))
}
