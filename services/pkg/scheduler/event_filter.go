package scheduler

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

// EventFilter selects which scheduler events a subscriber is interested in.
// A nil filter matches everything.
type EventFilter struct {
	// Include task events.
	Tasks bool

	// Include worker events.
	Workers bool

	// Include build events.
	Builds bool

	// Only include this build, its tasks and workers assigned to those tasks.
	BuildId string

	// Only include tasks with one of these statuses.
	TaskStatus []protocol.TaskStatus

	// Only include tasks and workers carrying all of these labels.
	Labels []string

	// Only include tasks and workers on this host.
	Hostname string

	// Suppress the initial snapshot.
	NoSnapshot bool
}

func NewEventFilter(request *protocol.StreamEventsRequest) *EventFilter {
	filter := &EventFilter{
		Tasks:      request.GetTasks(),
		Workers:    request.GetWorkers(),
		Builds:     request.GetBuilds(),
		BuildId:    request.GetBuildId(),
		TaskStatus: request.GetTaskStatus(),
		Labels:     request.GetLabels(),
		Hostname:   request.GetHostname(),
		NoSnapshot: request.GetNoSnapshot(),
	}

	// Selecting no event kinds selects all three.
	if !filter.Tasks && !filter.Workers && !filter.Builds {
		filter.Tasks = true
		filter.Workers = true
		filter.Builds = true
	}

	return filter
}

// Task status, labels and hostname do not apply to build metadata or removals.
func (f *EventFilter) MatchBuild(id string) bool {
	return f == nil || (f.Builds && (f.BuildId == "" || f.BuildId == id))
}

func (f *EventFilter) MatchTask(task *protocol.TaskInfo) bool {
	if f == nil {
		return true
	}

	if !f.Tasks {
		return false
	}

	if f.BuildId != "" && f.BuildId != task.GetBuildId() {
		return false
	}

	if f.Hostname != "" && f.Hostname != task.GetWorkerHostname() {
		return false
	}

	if len(f.TaskStatus) > 0 && !containsStatus(f.TaskStatus, task.GetStatus()) {
		return false
	}

	return containsAll(task.GetLabels(), f.Labels)
}

func (f *EventFilter) MatchWorker(worker *protocol.WorkerInfo) bool {
	if f == nil {
		return true
	}

	if !f.Workers {
		return false
	}

	if f.Hostname != "" && f.Hostname != worker.GetHostname() {
		return false
	}

	if f.BuildId != "" && f.BuildId != worker.GetTask().GetBuildId() {
		return false
	}

	if len(f.Labels) > 0 {
		labels, ok := NewPlatformFromProtobuf(worker.GetPlatform()).GetPropertiesForKey("label")
		if !ok || !containsAll(labels, f.Labels) {
			return false
		}
	}

	return true
}

// MatchEvent reports whether an incremental event should be forwarded.
func (f *EventFilter) MatchEvent(event *protocol.SchedulerEvent) bool {
	switch e := event.GetEvent().(type) {
	case *protocol.SchedulerEvent_Task:
		return f.MatchTask(e.Task)
	case *protocol.SchedulerEvent_Worker:
		return f.MatchWorker(e.Worker)
	case *protocol.SchedulerEvent_WorkerRemoved:
		// Removals carry no attributes to filter on. Subscribers that never saw
		// the worker simply ignore them.
		return f == nil || f.Workers
	case *protocol.SchedulerEvent_Build:
		return f.MatchBuild(e.Build.GetId())
	case *protocol.SchedulerEvent_BuildRemoved:
		return f.MatchBuild(e.BuildRemoved.GetId())
	default:
		return true
	}
}

func containsStatus(statuses []protocol.TaskStatus, status protocol.TaskStatus) bool {
	for _, candidate := range statuses {
		if candidate == status {
			return true
		}
	}
	return false
}

func containsAll(haystack, needles []string) bool {
	for _, needle := range needles {
		found := false
		for _, candidate := range haystack {
			if candidate == needle {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}
