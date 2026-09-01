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

	// Only include tasks belonging to this build.
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
		BuildId:    request.GetBuildId(),
		TaskStatus: request.GetTaskStatus(),
		Labels:     request.GetLabels(),
		Hostname:   request.GetHostname(),
		NoSnapshot: request.GetNoSnapshot(),
	}

	// Selecting neither kind selects both.
	if !filter.Tasks && !filter.Workers {
		filter.Tasks = true
		filter.Workers = true
	}

	return filter
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
