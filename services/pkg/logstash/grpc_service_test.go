package logstash

import (
	"context"
	"testing"
	"time"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// Minimal stand-in for protocol.LogStash_ReadLogServer. Embedding the
// grpc.ServerStream interface satisfies the methods the test never calls.
type fakeReadLogStream struct {
	grpc.ServerStream
	ctx       context.Context
	responses chan *protocol.ReadLogResponse
}

func (s *fakeReadLogStream) Context() context.Context {
	return s.ctx
}

func (s *fakeReadLogStream) Send(response *protocol.ReadLogResponse) error {
	s.responses <- response
	return nil
}

func newTestService(t *testing.T) (*LogStashService, LogStash) {
	t.Helper()

	config := new(MockLogStashConfig)
	config.On("MaxSize").Return(0x100000)
	stash := NewLogStash(config, afero.NewMemMapFs())

	return NewLogStashService(stash), stash
}

func testLine(message string) *protocol.LogLine {
	return &protocol.LogLine{
		Level:   protocol.LogLevel_INFO,
		Time:    timestamppb.Now(),
		Message: message,
	}
}

func TestReadLogWithoutFollowEndsAtEndOfLog(t *testing.T) {
	service, stash := newTestService(t)

	writer, err := stash.Append(logId1)
	assert.NoError(t, err)
	assert.NoError(t, writer.WriteLine(testLine("first")))
	// Deliberately left open: without follow the stream must still end.
	defer writer.Close()

	stream := &fakeReadLogStream{ctx: context.Background(), responses: make(chan *protocol.ReadLogResponse, 8)}

	done := make(chan error, 1)
	go func() {
		done <- service.ReadLog(&protocol.ReadLogRequest{Id: logId1}, stream)
	}()

	select {
	case err := <-done:
		assert.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("ReadLog without follow did not end at the end of the log")
	}

	assert.Len(t, stream.responses, 1)
}

func TestReadLogWithFollowStreamsUntilTheLogIsComplete(t *testing.T) {
	service, stash := newTestService(t)

	writer, err := stash.Append(logId1)
	assert.NoError(t, err)
	assert.NoError(t, writer.WriteLine(testLine("first")))

	stream := &fakeReadLogStream{ctx: context.Background(), responses: make(chan *protocol.ReadLogResponse, 8)}

	done := make(chan error, 1)
	go func() {
		done <- service.ReadLog(&protocol.ReadLogRequest{Id: logId1, Follow: true}, stream)
	}()

	select {
	case response := <-stream.responses:
		assert.Equal(t, "first", response.Loglines[0].Message)
	case <-time.After(2 * time.Second):
		t.Fatal("the first line never arrived")
	}

	// Written after the request started: this is the point of follow mode.
	assert.NoError(t, writer.WriteLine(testLine("second")))

	select {
	case response := <-stream.responses:
		assert.Equal(t, "second", response.Loglines[0].Message)
	case <-time.After(2 * time.Second):
		t.Fatal("a line written after the request started never arrived")
	}

	select {
	case <-done:
		t.Fatal("ReadLog ended while the log was still being written")
	case <-time.After(100 * time.Millisecond):
	}

	assert.NoError(t, writer.Close())

	select {
	case err := <-done:
		assert.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("ReadLog did not end after the log was complete")
	}
}

func TestReadLogWithInvalidIdIsInvalidArgument(t *testing.T) {
	service, _ := newTestService(t)

	stream := &fakeReadLogStream{ctx: context.Background(), responses: make(chan *protocol.ReadLogResponse, 8)}
	err := service.ReadLog(&protocol.ReadLogRequest{Id: "../../etc/passwd"}, stream)
	assert.Equal(t, codes.InvalidArgument, status.Code(err))
}
