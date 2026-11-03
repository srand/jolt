package protocol_test

import (
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
)

func TestBuildStatusIsCompleted(t *testing.T) {
	for value, name := range protocol.BuildStatus_name {
		status := protocol.BuildStatus(value)
		assert.Equal(t, status != protocol.BuildStatus_BUILD_ACCEPTED, status.IsCompleted(), name)
	}
}

func TestTaskStatusIsCompleted(t *testing.T) {
	inProgress := map[protocol.TaskStatus]bool{
		protocol.TaskStatus_TASK_CREATED:  true,
		protocol.TaskStatus_TASK_QUEUED:   true,
		protocol.TaskStatus_TASK_ASSIGNED: true,
		protocol.TaskStatus_TASK_RUNNING:  true,
	}
	for value, name := range protocol.TaskStatus_name {
		status := protocol.TaskStatus(value)
		assert.Equal(t, !inProgress[status], status.IsCompleted(), name)
	}
}

func TestTaskStatusIsCancellable(t *testing.T) {
	for value, name := range protocol.TaskStatus_name {
		status := protocol.TaskStatus(value)
		assert.Equal(t, status == protocol.TaskStatus_TASK_QUEUED, status.IsCancellable(), name)
	}
}
