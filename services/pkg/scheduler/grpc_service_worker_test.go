package scheduler

import (
	"context"
	"io"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"

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

// An executor that is cancelled when done is closed.
type cancelledExecutor struct {
	idleExecutor
	done chan struct{}
}

func (e *cancelledExecutor) Done() <-chan struct{} { return e.done }

type cancelledExecutorScheduler struct {
	Scheduler
	executor *cancelledExecutor
}

func (s *cancelledExecutorScheduler) NewExecutor(workerid, buildid string) (Executor, error) {
	return s.executor, nil
}

// A stream that receives updates without end, and cancels the executor
// once more updates have been received than the handler buffers.
type floodingTasksStream struct {
	grpc.ServerStream
	received int
	cancel   sync.Once
	executor *cancelledExecutor
}

func (s *floodingTasksStream) Context() context.Context { return context.Background() }

func (s *floodingTasksStream) Send(*protocol.TaskRequest) error { return nil }

func (s *floodingTasksStream) Recv() (*protocol.TaskUpdate, error) {
	s.received++
	if s.received > 200 {
		s.cancel.Do(func() { close(s.executor.done) })
	}
	return &protocol.TaskUpdate{
		Request: &protocol.TaskRequest{BuildId: "b"},
		Worker:  &protocol.WorkerAllocation{Id: "w"},
	}, nil
}

func getTasksReceiverRunning() bool {
	buf := make([]byte, 1<<20)
	return strings.Contains(string(buf[:runtime.Stack(buf, true)]), "(*workerService).GetTasks.func")
}

// The goroutine receiving updates exits when the handler returns, even
// if the handler has stopped reading updates and the buffer is full.
func TestGetTasksReceiverExitsWithHandler(t *testing.T) {
	executor := &cancelledExecutor{done: make(chan struct{})}
	stream := &floodingTasksStream{executor: executor}

	assert.NoError(t, NewWorkerService(nil, &cancelledExecutorScheduler{executor: executor}).GetTasks(stream))
	assert.Eventually(t, func() bool { return !getTasksReceiverRunning() }, 5*time.Second, 10*time.Millisecond)
}
