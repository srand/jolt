package scheduler

import (
	"context"
	"errors"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type TaskWalkFunc func(*Build, *Task) bool

type Build struct {
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

// Create a new build.
func NewBuildFromRequest(id string, request *protocol.BuildRequest) *Build {
	ctx, cancel := context.WithCancel(context.Background())

	build := &Build{
		ctx:         ctx,
		ctxCancel:   cancel,
		environment: request.Environment,
		id:          id,
		priority:    int(request.Priority),
		status:      protocol.BuildStatus_BUILD_ACCEPTED,
		tasks:       map[string]*Task{},
		queue: utils.NewUnicast[*Task](func(task *Task, platform interface{}) bool {
			if task.build.IsCancelled() {
				return false
			}
			pfm := platform.(*Platform)
			return pfm.Fulfills(task.Platform())
		}),
		buildObservers: NewBuildUpdateObservers(),
	}

	for _, task := range request.Environment.Tasks {
		task := NewTask(build, task)
		build.tasks[task.Identity()] = task
	}

	return build
}

// Returns the priority of the build.
func (b *Build) Priority() int {
	return b.priority
}

// Returns the number of queued tasks.
func (b *Build) NumQueuedTasks() int {
	return b.queue.Len()
}

// Cancel the build.
func (b *Build) Cancel() {
	b.status = protocol.BuildStatus_BUILD_CANCELLED
	b.ctxCancel()
}

// Close the build and all its tasks.
func (b *Build) Close() {
	b.ctxCancel()

	b.buildObservers.Close()

	tasks := []*Task{}
	b.WalkQueuedTasks(func(b *Build, t *Task) bool {
		tasks = append(tasks, t)
		return true
	})
	for _, task := range tasks {
		task.Close()
	}
	b.queue.Close()
}

// Returns a channel that is closed when the build is cancelled.
func (b *Build) Done() <-chan struct{} {
	return b.ctx.Done()
}

// Returns true if the build is cancelled.
func (b *Build) IsCancelled() bool {
	return b.status == protocol.BuildStatus_BUILD_CANCELLED
}

// Returns true if the build is terminal.
func (b *Build) IsTerminal() bool {
	return (!b.HasQueuedTask() && !b.HasRunningTask() && !b.HasObserver()) || (b.IsCancelled() && !b.HasRunningTask())
}

// Returns true if the build or one of its tasks has an observer.
func (b *Build) HasObserver() bool {
	if b.buildObservers.HasObserver() {
		return true
	}

	task := b.FindQueuedTask(func(b *Build, t *Task) bool {
		return t.HasObserver()
	})

	return task != nil
}

// Returns true if the build has a queued task.
func (b *Build) HasQueuedTask() bool {
	return !b.queue.Empty()
}

// Returns true if the build has a running task.
func (b *Build) HasRunningTask() bool {
	return b.queue.HasUnackedData()
}

// Returns the identity of the build.
func (b *Build) Id() string {
	return b.id
}

// Schedule one the build's tasks for execution.
// Returns the task and an observer for task updates.
// Returns an error if the task does not exist.
func (b *Build) ScheduleTask(identity string) (*Task, TaskUpdateObserver, error) {
	task, ok := b.tasks[identity]
	if !ok {
		return nil, nil, utils.NotFoundError
	}

	observer := task.NewUpdateObserver()
	b.queue.Send(task)
	return task, observer, nil
}

// Cancel a task.
func (b *Build) CancelTask(identity string) error {
	task, ok := b.tasks[identity]
	if !ok {
		return utils.NotFoundError
	}

	return task.Cancel()
}

// Returns the queued task with the given identity, or nil.
func (b *Build) FindQueuedTask(walkFn TaskWalkFunc) *Task {
	var lastTask *Task

	if b.WalkQueuedTasks(func(b *Build, t *Task) bool {
		lastTask = t
		return !walkFn(b, t)
	}) {
		return nil
	}

	return lastTask
}

// Iterate over all tasks.
// Returns false if the walk was aborted by the walkFn returning false.
func (b *Build) WalkTasks(walkFn TaskWalkFunc) bool {
	for _, task := range b.tasks {
		if !walkFn(b, task) {
			return false
		}
	}
	return true
}

// Iterate over all queued tasks.
// Returns false if the walk was aborted by the walkFn returning false.
func (b *Build) WalkQueuedTasks(walkFn TaskWalkFunc) bool {
	return b.queue.Walk(func(unicast *utils.Unicast[*Task], task *Task) bool {
		return walkFn(b, task)
	})
}

// Creates a new task executor for the build.
func (b *Build) NewExecutor(scheduler Scheduler, platform *Platform) (Executor, error) {
	if b.IsCancelled() {
		return nil, errors.New("Build is cancelled")
	}
	consumer := b.queue.NewConsumer(platform)
	return NewExecutor(scheduler, consumer), nil
}

// Create a new build update observer.
func (b *Build) NewUpdateObserver() BuildUpdateObserver {
	return b.buildObservers.NewObserver()
}
