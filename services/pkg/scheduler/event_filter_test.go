package scheduler

import (
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
)

func TestEventFilterMatchTask(t *testing.T) {
	task := &protocol.TaskInfo{
		BuildId:        "build",
		WorkerHostname: "host",
		Status:         protocol.TaskStatus_TASK_RUNNING,
		Labels:         []string{"fast", "linux"},
	}

	for name, test := range map[string]struct {
		filter *EventFilter
		want   bool
	}{
		"nil filter":        {nil, true},
		"tasks":             {&EventFilter{Tasks: true}, true},
		"no tasks":          {&EventFilter{Workers: true, Builds: true}, false},
		"build":             {&EventFilter{Tasks: true, BuildId: "build"}, true},
		"other build":       {&EventFilter{Tasks: true, BuildId: "other"}, false},
		"lesser build":      {&EventFilter{Tasks: true, BuildId: "a"}, false},
		"greater build":     {&EventFilter{Tasks: true, BuildId: "z"}, false},
		"host":              {&EventFilter{Tasks: true, Hostname: "host"}, true},
		"other host":        {&EventFilter{Tasks: true, Hostname: "other"}, false},
		"lesser host":       {&EventFilter{Tasks: true, Hostname: "a"}, false},
		"greater host":      {&EventFilter{Tasks: true, Hostname: "z"}, false},
		"status":            {&EventFilter{Tasks: true, TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_QUEUED, protocol.TaskStatus_TASK_RUNNING}}, true},
		"other status":      {&EventFilter{Tasks: true, TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_QUEUED}}, false},
		"label":             {&EventFilter{Tasks: true, Labels: []string{"linux"}}, true},
		"labels":            {&EventFilter{Tasks: true, Labels: []string{"linux", "fast"}}, true},
		"missing label":     {&EventFilter{Tasks: true, Labels: []string{"linux", "slow"}}, false},
		"everything":        {&EventFilter{Tasks: true, BuildId: "build", Hostname: "host", TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_RUNNING}, Labels: []string{"fast"}}, true},
		"everything but id": {&EventFilter{Tasks: true, BuildId: "other", Hostname: "host", TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_RUNNING}, Labels: []string{"fast"}}, false},
	} {
		assert.Equal(t, test.want, test.filter.MatchTask(task), name)
		event := &protocol.SchedulerEvent{Event: &protocol.SchedulerEvent_Task{Task: task}}
		assert.Equal(t, test.want, test.filter.MatchEvent(event), name)
	}
}

func TestEventFilterMatchWorker(t *testing.T) {
	platform := NewPlatform()
	platform.AddProperty("label", "fast")
	platform.AddProperty("label", "linux")
	worker := &protocol.WorkerInfo{
		Hostname: "host",
		Platform: platform.Protobuf(),
		Task:     &protocol.TaskInfo{BuildId: "build"},
	}

	for name, test := range map[string]struct {
		filter *EventFilter
		want   bool
	}{
		"nil filter":    {nil, true},
		"workers":       {&EventFilter{Workers: true}, true},
		"no workers":    {&EventFilter{Tasks: true, Builds: true}, false},
		"host":          {&EventFilter{Workers: true, Hostname: "host"}, true},
		"other host":    {&EventFilter{Workers: true, Hostname: "other"}, false},
		"lesser host":   {&EventFilter{Workers: true, Hostname: "a"}, false},
		"greater host":  {&EventFilter{Workers: true, Hostname: "z"}, false},
		"build":         {&EventFilter{Workers: true, BuildId: "build"}, true},
		"other build":   {&EventFilter{Workers: true, BuildId: "other"}, false},
		"lesser build":  {&EventFilter{Workers: true, BuildId: "a"}, false},
		"greater build": {&EventFilter{Workers: true, BuildId: "z"}, false},
		"label":         {&EventFilter{Workers: true, Labels: []string{"linux"}}, true},
		"labels":        {&EventFilter{Workers: true, Labels: []string{"linux", "fast"}}, true},
		"missing label": {&EventFilter{Workers: true, Labels: []string{"linux", "slow"}}, false},
		// Task status only applies to tasks
		"status": {&EventFilter{Workers: true, TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_QUEUED}}, true},
	} {
		assert.Equal(t, test.want, test.filter.MatchWorker(worker), name)
		event := &protocol.SchedulerEvent{Event: &protocol.SchedulerEvent_Worker{Worker: worker}}
		assert.Equal(t, test.want, test.filter.MatchEvent(event), name)
	}
}

func TestEventFilterMatchWorkerWithoutLabels(t *testing.T) {
	idle := &protocol.WorkerInfo{Hostname: "host"}
	assert.True(t, (&EventFilter{Workers: true}).MatchWorker(idle))
	assert.False(t, (&EventFilter{Workers: true, Labels: []string{"fast"}}).MatchWorker(idle))

	// An idle worker has no task, and so no build
	assert.False(t, (&EventFilter{Workers: true, BuildId: "build"}).MatchWorker(idle))
}

func TestEventFilterMatchWorkerRemoved(t *testing.T) {
	// Removals carry no attributes, so only the event kind is filtered.
	event := &protocol.SchedulerEvent{Event: &protocol.SchedulerEvent_WorkerRemoved{WorkerRemoved: &protocol.WorkerRemoved{}}}
	assert.True(t, (*EventFilter)(nil).MatchEvent(event))
	assert.True(t, (&EventFilter{Workers: true, Hostname: "other", BuildId: "other", Labels: []string{"other"}}).MatchEvent(event))
	assert.False(t, (&EventFilter{Tasks: true, Builds: true}).MatchEvent(event))
}

func TestEventFilterMatchOtherEvents(t *testing.T) {
	// Events of other kinds, such as snapshots, are always forwarded.
	event := &protocol.SchedulerEvent{Event: &protocol.SchedulerEvent_Snapshot{Snapshot: &protocol.Snapshot{}}}
	assert.True(t, (&EventFilter{}).MatchEvent(event))
}
