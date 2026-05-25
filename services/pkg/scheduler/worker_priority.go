package scheduler

import (
	"context"
	"sync"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/log"
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

	// The task platform properties of the worker, i.e.
	// the properties that must be fulfilled by the tasks.
	taskPlatform *Platform

	// The scheduler that the worker belongs to.
	scheduler *priorityScheduler

	// The channel that receives builds to be executed by the worker.
	builds chan Build

	// Protects closing of the builds channel.
	mu     sync.Mutex
	closed bool
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
	w.mu.Lock()
	if !w.closed {
		w.closed = true
		close(w.builds)
	}
	w.mu.Unlock()
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

// Returns the platform properties of the worker.
func (w *priorityWorker) TaskPlatform() *Platform {
	return w.taskPlatform
}

// Returns a string representation of the worker.
// By default, the string representation is the hostname of the worker.
// If the hostname is not available, the ID of the worker is returned.
func (w *priorityWorker) String() string {
	hostname := w.platform.GetHostname()
	if hostname != "" {
		return hostname
	}

	return w.Id()
}

// Returns a channel that receives tasks to be executed by the worker.
func (w *priorityWorker) Builds() chan Build {
	return w.builds
}

// Post a task to the worker.
func (w *priorityWorker) Post(build Build) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.closed {
		log.Errorf("build could not be delivered: worker closed")
		return
	}
	select {
	case w.builds <- build:
	default:
		log.Errorf("build could not be delivered: channel full")
	}
}
