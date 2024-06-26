package scheduler

// Interface for executors.
//
// An executors is an applications that runs an individual task.
// Typically, this is the same version of the Jolt client that started a build,
// invoked with a special command to receive tasks from the scheduler.
//
// The worker GRPC service uses the executor interface to exchange information
// between the scheduler and the executor.
type Executor interface {
	// Called to acknowledge that a task has been completed.
	// Must be called regardless if the task was successful or not.
	// If no acknowledgement is given after executing a task, the task
	// will be redistributed to another executor if the original executor
	// is terminated.
	Acknowledge()

	// Return the task that has been delivered to the consumer but not yet acknowledged.
	// If no task is pending, nil is returned.
	Unacknowledged() *Task

	// Unregister this executor.
	// If a task is in progress, that task is redistributed to another executor.
	Close()

	// Channel that is closed when the executor has terminated.
	Done() <-chan struct{}

	// The platform properties of the worker.
	Platform() *Platform

	// A channel where task execution requests are sent by the scheduler.
	Tasks() chan *Task
}
