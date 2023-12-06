package scheduler

import (
	"context"

	"github.com/google/uuid"
)

// A worker associated with the priority scheduler.
type priorityWorker struct {
	// The context of the worker.
	ctx context.Context
	// The function to cancel the worker.
	cancel func()

	// The ID of the worker.
	id uuid.UUID

	// The platform properties of the worker.
	platform *Platform

	// The scheduler that the worker belongs to.
	scheduler *priorityScheduler

	// The channel that receives tasks to be executed by the worker.
	tasks chan *Task
}

// Acknowledge that the worker has received and handled the task.
func (w *priorityWorker) Acknowledge() {
	w.scheduler.releaseWorker(w)
}

// Cancel the worker and stop it from receiving new tasks.
func (w *priorityWorker) Cancel() {
	w.cancel()
}

// Close the worker.
// Unregisters the worker from the scheduler.
func (w *priorityWorker) Close() {
	w.cancel()
	close(w.tasks)
	w.scheduler.removeWorker(w)
}

// Returns a channel that is closed when the worker is cancelled.
func (w *priorityWorker) Done() <-chan struct{} {
	return w.ctx.Done()
}

// Returns the ID of the worker.
func (w *priorityWorker) Id() string {
	return w.id.String()
}

// Returns the platform properties of the worker.
func (w *priorityWorker) Platform() *Platform {
	return w.platform
}

// Returns a string representation of the worker.
func (w *priorityWorker) String() string {
	hostnames, ok := w.Platform().GetPropertiesForKey("worker.hostname")
	if !ok {
		return w.Id()
	}
	if len(hostnames) > 0 {
		return hostnames[0]
	}
	return w.Id()
}

// Returns a channel that receives tasks to be executed by the worker.
func (w *priorityWorker) Tasks() chan *Task {
	return w.tasks
}
