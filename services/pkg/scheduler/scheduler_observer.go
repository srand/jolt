package scheduler

import "github.com/srand/jolt/scheduler/pkg/protocol"

type SchedulerObserver interface {
	// When the client has requested the task to be executed
	TaskScheduled(*Task)

	// When the task's status has changed
	TaskStatusChanged(*Task, protocol.TaskStatus)

	// When a worker has connected and registered with the scheduler
	WorkerEnlisted(Worker)

	// When a worker has disconnected and been unregistered
	WorkerDelisted(Worker)
}
