package scheduler

import (
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
)

type Build interface {
	// Returns the build environment as provided by the client.
	Environment() *protocol.BuildEnvironment

	// Returns the priority of the build.
	Priority() int

	// Returns the time of scheduling.
	ScheduledAt() time.Time

	// Returns the number of queued tasks.
	NumQueuedTasks() int

	// Returns the number of running tasks.
	NumRunningTasks() int

	// Cancel the build.
	Cancel()

	// Close the build and all its tasks.
	Close()

	// Returns a channel that is closed when the build is cancelled.
	Done() <-chan struct{}

	// Returns true if the build is cancelled.
	IsCancelled() bool

	// Returns true if the build is in a terminal state, but may have outstanding work to complete.
	IsDone() bool

	// Returns true if the build is terminal.
	IsTerminal() bool

	// Returns true if the build or one of its tasks has an observer.
	HasObserver() bool

	// Returns true if the build has a queued task.
	HasQueuedTask() bool

	// Returns true if the build has a running task.
	HasRunningTask() bool

	// Returns the identity of the build.
	Id() string

	// Returns the build status.
	Status() protocol.BuildStatus

	// Returns true if the build should stream logs back to the client.
	LogStreamEnabled() bool
}
