package scheduler

// A worker that receives and executes tasks.
type Worker interface {

	// Acknowledge that task has been executed,
	// and release the worker for new work.
	Acknowledge()

	// Cancel worker, may be called by anyone
	Cancel()

	// Unregister worker with scheduler.
	// Called from gRPC service when connection is closed.
	Close()

	// Channel indicating that the worker is cancelled and will be disconnecting
	Done() <-chan struct{}

	// UUID identity of worker
	Id() string

	// The platform properties of the worker.
	// By default, all workers must provide:
	//  - node.os = <operating system>
	//  - node.arch = <cpu architecture>
	//  - worker.hostname = <hostname>
	Platform() *Platform

	// The task platform properties of the worker.
	// The properties that must be fulfilled by the tasks.
	TaskPlatform() *Platform

	// A channel where task execution requests are sent by the scheduler.
	// The worker shall launch an executor to execute the task.
	// The executor may execute additinonal compatible tasks.
	Tasks() chan *Task

	// Post a task to the worker.
	Post(*Task)
}
