package scheduler

import "context"

// Main scheduler interface
type Scheduler interface {
	// Cancel
	CancelBuild(build string) error

	// Find build
	GetBuild(buildId string) *Build

	// Schedule new build
	ScheduleBuild(*Build) error

	// Schedule task to be executed.
	// A build must have been registered first and its identifier must be provided.
	ScheduleTask(buildId, taskId string) (TaskUpdateObserver, error)

	///////////////////////////////////////////////////////////////////////////

	// Register a new worker with the scheduler.
	// The returned worker must be Close():ed when it no longer wishes to accept
	// new build requests. Closing unregisters the worker in the scheduler.
	NewWorker(*Platform) (Worker, error)

	///////////////////////////////////////////////////////////////////////////

	// Register a new build executor.
	// The returned executor must be Close():ed when it no longer wishes to
	// accept new task requests.
	NewExecutor(workerid, buildid string) (Executor, error)

	///////////////////////////////////////////////////////////////////////////

	// Run scheduler
	Run(ctx context.Context)

	// Force scheduler to re-evaluate it's builds and tasks (mostly for debug)
	Reschedule()
}
