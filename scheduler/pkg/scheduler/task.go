package scheduler

import (
	"sync"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

// A task to be executed by a worker.
type Task struct {
	sync.RWMutex

	// The build that the task belongs to.
	build *Build

	// The platform that the task should be executed on.
	platform *Platform

	// The current status of the task.
	status protocol.TaskStatus

	// The original client request.
	task *protocol.Task

	// Observers to be notified of task updates.
	// Includes status and log updates.
	updateObservers TaskUpdateObservers
}

// Create a new task.
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

// Returns the influende identity of the task.
func (t *Task) Identity() string {
	return t.task.Identity
}

// Returns the instance ID of the task.
func (t *Task) Instance() string {
	return t.task.Instance
}

// Returns the platform properties of the task.
func (t *Task) Platform() *Platform {
	return t.platform
}

// Returns the build that the task belongs to.
func (t *Task) Build() *Build {
	return t.build
}

// Returns the name of the task.
func (t *Task) Name() string {
	return t.task.Name
}

// Returns true if the task is completed.
// A task is not completed if it is queued or running.
func (t *Task) IsCompleted() bool {
	t.RLock()
	defer t.RUnlock()
	return t.status.IsCompleted()
}

// Returns true if the task status is being monitored.
func (t *Task) HasObserver() bool {
	return t.updateObservers.HasObserver()
}

// Create a new task update observer.
func (t *Task) NewUpdateObserver() TaskUpdateObserver {
	return t.updateObservers.NewObserver()
}

// Post a task update to all task observers.
func (t *Task) PostUpdate(update *protocol.TaskUpdate) {
	statusChanged := t.setStatus(update.Status)
	if t.build.logstream {
		if !statusChanged {
			if len(update.Loglines) <= 0 {
				return
			}
			update.Status = t.status
		}
		t.updateObservers.Post(update)
	} else if statusChanged {
		// Copy update
		update := &protocol.TaskUpdate{
			Request:  update.Request,
			Status:   update.Status,
			Errors:   update.Errors,
			Worker:   update.Worker,
			Loglines: update.Loglines,
		}

		if !t.build.logstream {
			update.Loglines = []*protocol.LogLine{}
		}

		t.updateObservers.Post(update)
	}
}

// Post a task status update to all task observers.
func (t *Task) PostStatusUpdate(status protocol.TaskStatus) {
	t.PostUpdate(&protocol.TaskUpdate{
		Request: &protocol.TaskRequest{
			BuildId: t.build.Id(),
			TaskId:  t.Identity(),
		},
		Status: status,
	})
}

// Set the status of the task.
// The status can only be changed if the current status is queued or running.
// Returns true if the status was changed.
func (t *Task) setStatus(status protocol.TaskStatus) bool {
	t.Lock()
	defer t.Unlock()

	// Ignore identical statuses
	if status == t.status {
		return false
	}

	// Can only transition to cancelled from queued.
	if status == protocol.TaskStatus_TASK_CANCELLED && t.status != protocol.TaskStatus_TASK_QUEUED {
		log.Debugf("err - task - id: %s, status: %v - new status rejected: %v", t.Identity(), t.status, status)
		return false
	}

	switch t.status {
	case protocol.TaskStatus_TASK_QUEUED, protocol.TaskStatus_TASK_RUNNING:
		if t.status != status {
			t.status = status
			return true
		}
		return false

	default:
		// Allow the task to be restarted if it has completed.
		if status == protocol.TaskStatus_TASK_QUEUED {
			t.status = status
			return true
		}

		log.Debugf("err - task - id: %s, status: %v - new status rejected: %v", t.Identity(), t.status, status)
		return false
	}
}

func (t *Task) Status() protocol.TaskStatus {
	t.RLock()
	defer t.RUnlock()
	return t.status
}

// Cancel the task.
func (t *Task) Cancel() error {
	t.PostStatusUpdate(protocol.TaskStatus_TASK_CANCELLED)
	return nil
}

// Close the task and cancel all observers.
func (t *Task) Close() {
	t.Cancel()
	t.updateObservers.Close()
}
