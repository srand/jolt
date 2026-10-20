package scheduler

import (
	"context"

	"github.com/srand/jolt/scheduler/pkg/protocol"
)

// Main scheduler interface.
type Scheduler interface {
	// Cancel a build with the given identifier.
	CancelBuild(build string) error

	// Create a new build with the given identifier.
	NewBuild(id string, request *protocol.BuildRequest) Build

	// Get build with the given identifier.
	GetBuild(buildId string) (Build, error)

	// Register a new build with the scheduler.
	ScheduleBuild(Build) (BuildUpdateObserver, error)

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

	// Get information about running builds. If tasks is true, also include
	// information about the tasks of each build.
	ListBuilds(tasks bool) *protocol.ListBuildsResponse

	// Get information about connected workers.
	ListWorkers() *protocol.ListWorkersResponse
}

// Worker platform dimensions used for statistics. Worker-specific properties
// such as hostnames and IDs are deliberately excluded so workers are aggregated.
type WorkerPlatform struct {
	OS   string
	Arch string

	// Sorted, comma-separated nonempty Jolt labels, or "unknown" if absent.
	Label string
}

// Worker counts for a platform. Active workers are connected workers that are
// not available for scheduling, including workers awaiting acknowledgement.
type WorkerStatistics struct {
	Workers       int64
	ActiveWorkers int64
}

// Scheduler statistics
type SchedulerStatistics struct {
	// Number of workers
	Workers int64

	// Worker counts grouped by operating system, CPU architecture and Jolt label set
	WorkersByPlatform map[WorkerPlatform]WorkerStatistics

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
