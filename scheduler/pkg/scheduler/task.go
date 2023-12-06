package scheduler

import (
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

type Task struct {
	build           *Build
	platform        *Platform
	status          protocol.TaskStatus
	task            *protocol.Task
	updateObservers TaskUpdateObservers
}

func NewTask(build *Build, task *protocol.Task) *Task {
	platform := (*Platform)(task.Platform)
	if platform == nil {
		platform = &Platform{}
	}

	return &Task{
		build:           build,
		platform:        platform,
		status:          protocol.TaskStatus_TASK_QUEUED,
		task:            task,
		updateObservers: NewTaskUpdateObservers(),
	}
}

func (t *Task) Identity() string {
	return t.task.Identity
}

func (t *Task) Platform() *Platform {
	return t.platform
}

func (t *Task) Build() *Build {
	return t.build
}

func (t *Task) Name() string {
	return t.task.Name
}

func (t *Task) IsCompleted() bool {
	return t.status.IsCompleted()
}

func (t *Task) HasObserver() bool {
	return t.updateObservers.HasObserver()
}

func (t *Task) NewUpdateObserver() TaskUpdateObserver {
	return t.updateObservers.NewObserver()
}

func (t *Task) PostUpdate(update *protocol.TaskUpdate) {
	if t.SetStatus(update.Status) {
		t.updateObservers.Post(update)
	}
}

func (t *Task) SetStatus(status protocol.TaskStatus) bool {
	switch t.status {
	case protocol.TaskStatus_TASK_QUEUED, protocol.TaskStatus_TASK_RUNNING:
		t.status = status
		return true

	default:
		log.Debugf("New task status %v rejected, status already %v", status, t.status)
		return false
	}
}

func (t *Task) Cancel() error {
	t.PostUpdate(&protocol.TaskUpdate{
		Request: &protocol.TaskRequest{
			BuildId: t.build.Id(),
			TaskId:  t.Identity(),
		},
		Status: protocol.TaskStatus_TASK_CANCELLED,
	})
	return nil
}

func (t *Task) Close() {
	t.Cancel()
	t.updateObservers.Close()
}
