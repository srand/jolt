package scheduler

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type TaskWalkFunc func(*priorityBuild, *Task) bool

type priorityBuild struct {
	sync.RWMutex

	// The context of the build.
	// Cancel the context to cancel the build.
	ctx context.Context
	// Cancel function for the build context.
	ctxCancel func()

	// The build environment as provided by the client.
	environment *protocol.BuildEnvironment

	// The unique identifier of the build.
	// This is the SHA1 hash of the build request.
	id string

	// The priority of the build.
	priority int

	// The time of scheduling.
	scheduledAt time.Time

	// Stream log lines to client
	logstream bool

	// The current status of the build.
	status protocol.BuildStatus

	// All tasks that the build consists of.
	tasks map[string]*Task

	// The tasks that have been queued for execution.
	// Tasks are executed in FIFO order if there are workers available.
	// If there is no eligible worker for a task, that task will remain
	// queued until a worker becomes available. Meanwhile, other tasks may
	// jump ahead in the queue.
	queue *utils.Unicast[*Task]

	// Build update observers
	buildObservers BuildUpdateObservers
}

// Returns the build environment as provided by the client.
func (b *priorityBuild) Environment() *protocol.BuildEnvironment {
	b.RLock()
	defer b.RUnlock()
	return b.environment
}

// Returns the priority of the build.
func (b *priorityBuild) Priority() int {
	b.RLock()
	defer b.RUnlock()
	return b.priority
}

// Returns the time of scheduling.
func (b *priorityBuild) ScheduledAt() time.Time {
	b.RLock()
	defer b.RUnlock()
	return b.scheduledAt
}

// Returns the number of queued tasks.
func (b *priorityBuild) NumQueuedTasks() int {
	b.RLock()
	defer b.RUnlock()
	return b.queue.Len()
}

// Returns the number of queued tasks.
func (b *priorityBuild) NumRunningTasks() int {
	b.RLock()
	defer b.RUnlock()
	return b.queue.NumUnackedData()
}

// Cancel the build.
func (b *priorityBuild) Cancel() {
	b.Lock()
	defer b.Unlock()
	b.status = protocol.BuildStatus_BUILD_CANCELLED

	// Attempt to cancel all tasks.
	// Tasks that are in progress or have already finished will be ignored.
	for _, task := range b.tasks {
		task.Cancel()
	}

	b.ctxCancel()
}

// Close the build and all its tasks.
func (b *priorityBuild) Close() {
	b.RLock()
	defer b.RUnlock()

	b.ctxCancel()
	b.buildObservers.Close()

	tasks := []*Task{}
	b.WalkQueuedTasks(func(b *priorityBuild, t *Task) bool {
		tasks = append(tasks, t)
		return true
	})

	for _, task := range tasks {
		task.Close()
	}

	b.queue.Close()
	b.queue = nil
	b.environment = nil
	b.tasks = nil
}

// Returns a channel that is closed when the build is cancelled.
func (b *priorityBuild) Done() <-chan struct{} {
	return b.ctx.Done()
}

// Returns true if the build is cancelled.
func (b *priorityBuild) IsCancelled() bool {
	b.RLock()
	defer b.RUnlock()
	return b.isCancelled()
}

func (b *priorityBuild) isCancelled() bool {
	return b.status == protocol.BuildStatus_BUILD_CANCELLED
}

// Returns true if the build is in a terminal state, but may have outstanding work to complete.
func (b *priorityBuild) IsDone() bool {
	b.RLock()
	defer b.RUnlock()
	return b.status != protocol.BuildStatus_BUILD_ACCEPTED
}

// Returns true if the build is terminal.
func (b *priorityBuild) IsTerminal() bool {
	return (!b.HasQueuedTask() && !b.HasRunningTask() && !b.HasObserver()) || (b.IsCancelled() && !b.HasRunningTask())
}

// Returns true if the build or one of its tasks has an observer.
func (b *priorityBuild) HasObserver() bool {
	b.RLock()
	defer b.RUnlock()

	if b.buildObservers == nil {
		return false
	}

	if b.buildObservers.HasObserver() {
		return true
	}

	task := b.FindQueuedTask(func(b *priorityBuild, t *Task) bool {
		return t.HasObserver()
	})

	return task != nil
}

// Returns true if the build has a queued task.
func (b *priorityBuild) HasQueuedTask() bool {
	b.RLock()
	defer b.RUnlock()
	if b.queue == nil {
		return false
	}
	return !b.queue.Empty()
}

// Returns true if the build has a running task.
func (b *priorityBuild) HasRunningTask() bool {
	b.RLock()
	defer b.RUnlock()
	if b.queue == nil {
		return false
	}
	return b.queue.HasUnackedData()
}

// Returns the identity of the build.
func (b *priorityBuild) Id() string {
	return b.id
}

// Schedule one the build's tasks for execution.
// Returns the task and an observer for task updates.
// Returns an error if the task does not exist.
func (b *priorityBuild) ScheduleTask(identity string) (*Task, TaskUpdateObserver, error) {
	b.Lock()
	defer b.Unlock()

	if b.isCancelled() {
		return nil, nil, errors.New("Build is cancelled")
	}

	task, ok := b.tasks[identity]
	if !ok {
		return nil, nil, utils.ErrNotFound
	}

	switch task.Status() {
	case protocol.TaskStatus_TASK_QUEUED, protocol.TaskStatus_TASK_RUNNING:
		// Task is already queued or running.
	default:
		// The task has completed or is cancelled.
		// Restart the task so that the client can observe it again.
		// In most cases, the task will only be downloaded on the worker, or skipped.
		task.PostStatusUpdate(protocol.TaskStatus_TASK_QUEUED)
	}

	observer := task.NewUpdateObserver()

	// Add the task to the queue.
	// The task will be executed when a worker becomes available.
	// Duplicate tasks are not added to the queue.
	b.queue.Send(task)

	return task, observer, nil
}

// Cancel a task.
func (b *priorityBuild) CancelTask(identity string) error {
	b.Lock()
	defer b.Unlock()

	task, ok := b.tasks[identity]
	if !ok {
		return utils.ErrNotFound
	}

	return task.Cancel()
}

// Returns the queued task with the given identity, or nil.
func (b *priorityBuild) FindQueuedTask(walkFn TaskWalkFunc) *Task {
	b.RLock()
	defer b.RUnlock()

	var lastTask *Task

	if b.WalkQueuedTasks(func(b *priorityBuild, t *Task) bool {
		lastTask = t
		return !walkFn(b, t)
	}) {
		return nil
	}

	return lastTask
}

// Return the build status
func (b *priorityBuild) Status() protocol.BuildStatus {
	b.RLock()
	defer b.RUnlock()
	return b.status
}

// Iterate over all tasks.
// Returns false if the walk was aborted by the walkFn returning false.
func (b *priorityBuild) WalkTasks(walkFn TaskWalkFunc) bool {
	b.RLock()
	defer b.RUnlock()

	for _, task := range b.tasks {
		if !walkFn(b, task) {
			return false
		}
	}
	return true
}

// Iterate over all queued tasks.
// Returns false if the walk was aborted by the walkFn returning false.
func (b *priorityBuild) WalkQueuedTasks(walkFn TaskWalkFunc) bool {
	b.RLock()
	defer b.RUnlock()

	return b.queue.Walk(func(unicast *utils.Unicast[*Task], task *Task) bool {
		return walkFn(b, task)
	})
}

// Creates a new task executor for the build.
func (b *priorityBuild) NewExecutor(scheduler Scheduler, worker Worker) (Executor, error) {
	if b.IsCancelled() || b.queue == nil {
		return nil, errors.New("Build is cancelled")
	}
	consumer, err := b.queue.NewConsumerWithItem(worker)
	if err != nil {
		return nil, err
	}
	return NewExecutor(scheduler, worker.Platform(), consumer), nil
}

// Create a new build update observer.
func (b *priorityBuild) NewUpdateObserver() BuildUpdateObserver {
	// Locking is not necessary here because the build observers have their own locks.
	return b.buildObservers.NewObserver()
}

// Returns true if the build should stream logs back to the client.
func (b *priorityBuild) LogStreamEnabled() bool {
	return b.logstream
}
