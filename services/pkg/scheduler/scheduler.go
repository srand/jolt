package scheduler

import "context"

// Main scheduler interface.
type Scheduler interface {
	// Cancel a build with the given identifier.
	CancelBuild(build string) error

	// Get build with the given identifier.
	GetBuild(buildId string) *Build

	// Register a new build with the scheduler.
	ScheduleBuild(*Build) (BuildUpdateObserver, error)

	// Schedule a task belonging to a build for execution.
	// A build must have been registered first and its identifier must be provided.
	ScheduleTask(buildId, taskId string) (TaskUpdateObserver, error)

	///////////////////////////////////////////////////////////////////////////

	// Register a new worker with the scheduler.
	// The returned worker must be Close():ed when it no longer wishes to accept
	// new build requests. Closing unregisters the worker in the scheduler.
	NewWorker(*Platform, *Platform) (Worker, error)

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

	// Get scheduler statistics
	Statistics() *SchedulerStatistics
}

// Scheduler statistics
type SchedulerStatistics struct {
	// Number of workers
	Workers int64

	// Number of builds in progress
	Builds int64

	// Number of completed builds
	CompletedBuilds int64

	// Total number of tasks that are queued
	QueuedTasks int64

	// Total number of tasks that are running
	RunningTasks int64

	// Total number of successful tasks
	SuccessfulTasks int64

	// Total number of failed tasks
	FailedTasks int64

	// Total number of completed tasks (successful or failed)
	CompletedTasks int64
}
