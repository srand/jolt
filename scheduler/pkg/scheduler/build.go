package scheduler

import (
	"context"
	"errors"

	"github.com/srand/jolt/scheduler/pkg"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type TaskWalkFunc func(*Build, *Task) bool

type Build struct {
	ctx         context.Context
	ctxCancel   func()
	environment *protocol.BuildEnvironment
	id          string
	status      protocol.BuildStatus
	tasks       map[string]*Task
	completed   uint
	queue       *utils.Unicast[*Task]
}

func NewBuildFromRequest(id string, request *protocol.BuildRequest) *Build {
	ctx, cancel := context.WithCancel(context.Background())

	build := &Build{
		ctx:         ctx,
		ctxCancel:   cancel,
		environment: request.Environment,
		id:          id,
		status:      protocol.BuildStatus_BUILD_ACCEPTED,
		tasks:       map[string]*Task{},
		queue: utils.NewUnicast[*Task](func(task *Task, platform interface{}) bool {
			if task.build.IsCancelled() {
				return false
			}
			pfm := platform.(*Platform)
			return pfm.Fulfills(task.Platform())
		}),
	}

	for _, task := range request.Environment.Tasks {
		task := NewTask(build, task)
		build.tasks[task.Identity()] = task
	}

	return build
}

func (b *Build) Cancel() {
	b.status = protocol.BuildStatus_BUILD_CANCELLED
	b.ctxCancel()
}

func (b *Build) Close() {
	b.ctxCancel()

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

func (b *Build) Done() <-chan struct{} {
	return b.ctx.Done()
}

func (b *Build) IsCancelled() bool {
	return b.status == protocol.BuildStatus_BUILD_CANCELLED
}

func (b *Build) IsTerminal() bool {
	return (!b.HasRunningTask() && !b.HasObserver() && !b.HasTasks()) || (b.IsCancelled() && !b.HasRunningTask())
}

func (b *Build) HasObserver() bool {
	task := b.FindQueuedTask(func(b *Build, t *Task) bool {
		return t.HasObserver()
	})
	return task != nil
}

func (b *Build) HasRunningTask() bool {
	return b.queue.HasUnackedData()
}

func (b *Build) HasTasks() bool {
	return !b.IsCancelled() && !b.queue.Empty()
}

func (b *Build) Id() string {
	return b.id
}

func (b *Build) ScheduleTask(identity string) (*Task, TaskUpdateObserver, error) {
	task, ok := b.tasks[identity]
	if !ok {
		return nil, nil, pkg.NotFoundError
	}

	observer := task.NewUpdateObserver()
	b.queue.Send(task)
	return task, observer, nil
}

func (b *Build) CancelTask(identity string) error {
	task, ok := b.tasks[identity]
	if !ok {
		return pkg.NotFoundError
	}

	return task.Cancel()
}

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

func (b *Build) WalkTasks(walkFn TaskWalkFunc) bool {
	for _, task := range b.tasks {
		if !walkFn(b, task) {
			return false
		}
	}
	return true
}

func (b *Build) WalkQueuedTasks(walkFn TaskWalkFunc) bool {
	return b.queue.Walk(func(unicast *utils.Unicast[*Task], task *Task) bool {
		return walkFn(b, task)
	})
}

func (b *Build) NewExecutor(scheduler Scheduler, platform *Platform) (Executor, error) {
	if b.IsCancelled() {
		return nil, errors.New("Build is cancelled")
	}
	consumer := b.queue.NewConsumer(platform)
	return NewExecutor(scheduler, consumer), nil
}
