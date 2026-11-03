package protocol_test

import (
	"testing"

	"buf.build/go/protovalidate"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"google.golang.org/protobuf/proto"
)

func sha1Hex(t *testing.T, data string) string {
	digest, err := utils.Sha1String(data)
	assert.NoError(t, err)
	return digest
}

// A build request as the Jolt client creates it.
func TestValidateAcceptsPythonBuildRequest(t *testing.T) {
	request := &protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{
			Client: &protocol.Client{Version: "0.9.400"},
			Workspace: &protocol.Workspace{
				Rootdir: "/workspace",
				Name:    "workspace",
				Files:   []*protocol.File{{Path: "build.jolt", Content: "..."}},
			},
			Parameters: []*protocol.Property{{Key: "config.x", Value: "y"}},
			Tasks: map[string]*protocol.Task{
				"a/b:x=1": {
					Name:     "a/b:x=1",
					Identity: sha1Hex(t, "a/b:x=1"),
					Instance: "0b1d5b4c-0f86-4b1e-9b8e-6c1b8a3a2c11",
					Platform: &protocol.Platform{
						Properties: []*protocol.Property{{Key: "node.os", Value: "linux"}},
					},
				},
			},
		},
		Logstream: true,
	}
	assert.NoError(t, protovalidate.Validate(request))
}

// A build request as schedulerctl mock build creates it.
func TestValidateAcceptsMockBuildRequest(t *testing.T) {
	request := &protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{
			Workspace: &protocol.Workspace{},
			Tasks: map[string]*protocol.Task{
				"t": {Name: "t", Identity: sha1Hex(t, "t")},
			},
		},
	}
	assert.NoError(t, protovalidate.Validate(request))
}

// The first message of an executor has no task.
func TestValidateAcceptsExecutorEnlist(t *testing.T) {
	update := &protocol.TaskUpdate{
		Request: &protocol.TaskRequest{BuildId: "b"},
		Worker:  &protocol.WorkerAllocation{Id: "w"},
	}
	assert.NoError(t, protovalidate.Validate(update))
}

// Older receivers must accept enum values added later.
func TestValidateAcceptsUnknownEnums(t *testing.T) {
	update := &protocol.TaskUpdate{
		Request:  &protocol.TaskRequest{BuildId: "b", TaskId: "ab"},
		Status:   protocol.TaskStatus(99),
		Loglines: []*protocol.LogLine{{Level: protocol.LogLevel(99)}},
	}
	assert.NoError(t, protovalidate.Validate(update))
}

// Worker properties are not validated.
func TestValidateAcceptsWorkerUpdate(t *testing.T) {
	update := &protocol.WorkerUpdate{
		Status: protocol.WorkerUpdate_ENLISTING,
		Platform: &protocol.Platform{
			Properties: []*protocol.Property{{Key: "", Value: "x"}},
		},
	}
	assert.NoError(t, protovalidate.Validate(update))
}

func TestValidateRejects(t *testing.T) {
	identity := sha1Hex(t, "t")
	environment := func(key string, task *protocol.Task) *protocol.BuildRequest {
		return &protocol.BuildRequest{
			Environment: &protocol.BuildEnvironment{
				Tasks: map[string]*protocol.Task{key: task},
			},
		}
	}

	tests := map[string]proto.Message{
		"empty task name":         environment("t", &protocol.Task{Identity: identity}),
		"uppercase task identity": environment("t", &protocol.Task{Name: "t", Identity: "ABC"}),
		"empty task identity":     environment("t", &protocol.Task{Name: "t"}),
		"empty task key":          environment("", &protocol.Task{Name: "t", Identity: identity}),
		"no environment":          &protocol.BuildRequest{},
		"empty cancel build id":   &protocol.CancelBuildRequest{},
		"empty task build id":     &protocol.TaskRequest{TaskId: "ab"},
		"non-hex task id":         &protocol.TaskRequest{BuildId: "b", TaskId: "xyz"},
		"task update no request":  &protocol.TaskUpdate{},
		"empty log id":            &protocol.ReadLogRequest{},
	}

	for name, message := range tests {
		t.Run(name, func(t *testing.T) {
			assert.Error(t, protovalidate.Validate(message))
		})
	}
}
