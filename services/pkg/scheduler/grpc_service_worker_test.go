package scheduler

import (
	"context"
	"io"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// An executor that never receives tasks.
type idleExecutor struct {
	Executor
}

func (e *idleExecutor) Close()                {}
func (e *idleExecutor) Done() <-chan struct{} { return nil }
func (e *idleExecutor) Tasks() chan *Task     { return nil }

// A scheduler that hands out idle executors.
type executorScheduler struct {
	Scheduler
}

func (s *executorScheduler) NewExecutor(workerid, buildid string) (Executor, error) {
	return &idleExecutor{}, nil
}

type received struct {
	update *protocol.TaskUpdate
	err    error
}

// A stream that returns a fixed sequence of received messages.
type scriptedTasksStream struct {
	grpc.ServerStream
	messages []received
}

func (s *scriptedTasksStream) Context() context.Context { return context.Background() }

func (s *scriptedTasksStream) Send(*protocol.TaskRequest) error { return nil }

func (s *scriptedTasksStream) Recv() (*protocol.TaskUpdate, error) {
	if len(s.messages) == 0 {
		return nil, io.EOF
	}
	message := s.messages[0]
	s.messages = s.messages[1:]
	return message.update, message.err
}

// A message rejected after the executor enlisted ends the stream with
// the error, instead of a clean end of stream.
func TestGetTasksReturnsReceiveError(t *testing.T) {
	invalid := status.Error(codes.InvalidArgument, "validation error: request: value is required")
	stream := &scriptedTasksStream{messages: []received{
		{update: &protocol.TaskUpdate{
			Request: &protocol.TaskRequest{BuildId: "b"},
			Worker:  &protocol.WorkerAllocation{Id: "w"},
		}},
		{err: invalid},
	}}

	err := NewWorkerService(nil, &executorScheduler{}).GetTasks(stream)
	assert.Equal(t, codes.InvalidArgument, status.Code(err))
}

func TestGetTasksEndsCleanlyAtEOF(t *testing.T) {
	stream := &scriptedTasksStream{messages: []received{
		{update: &protocol.TaskUpdate{
			Request: &protocol.TaskRequest{BuildId: "b"},
			Worker:  &protocol.WorkerAllocation{Id: "w"},
		}},
	}}

	assert.NoError(t, NewWorkerService(nil, &executorScheduler{}).GetTasks(stream))
}
