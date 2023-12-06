package scheduler

import (
	"context"

	"github.com/google/uuid"
)

type roundRobinWorker struct {
	ctx       context.Context
	cancel    func()
	id        uuid.UUID
	platform  *Platform
	scheduler *roundRobinScheduler
	tasks     chan *Task
}

func (w *roundRobinWorker) Acknowledge() {
	w.scheduler.releaseWorker(w)
}

func (w *roundRobinWorker) Cancel() {
	w.cancel()
}

func (w *roundRobinWorker) Close() {
	w.cancel()
	close(w.tasks)
	w.scheduler.removeWorker(w)
}

func (w *roundRobinWorker) Done() <-chan struct{} {
	return w.ctx.Done()
}

func (w *roundRobinWorker) Id() string {
	return w.id.String()
}

func (w *roundRobinWorker) Platform() *Platform {
	return w.platform
}

func (w *roundRobinWorker) String() string {
	return w.Id()
}

func (w *roundRobinWorker) Tasks() chan *Task {
	return w.tasks
}
