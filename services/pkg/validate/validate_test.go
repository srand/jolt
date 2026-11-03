package validate_test

import (
	"context"
	"net"
	"testing"
	"time"

	"buf.build/gen/go/bufbuild/protovalidate/protocolbuffers/go/buf/validate"
	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	pkgvalidate "github.com/srand/jolt/scheduler/pkg/validate"
	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

type schedulerServer struct {
	protocol.UnimplementedSchedulerServer
	cancelled []string
}

func (s *schedulerServer) CancelBuild(ctx context.Context, req *protocol.CancelBuildRequest) (*protocol.CancelBuildResponse, error) {
	s.cancelled = append(s.cancelled, req.BuildId)
	return &protocol.CancelBuildResponse{}, nil
}

func (s *schedulerServer) ScheduleTask(req *protocol.TaskRequest, stream protocol.Scheduler_ScheduleTaskServer) error {
	return stream.Send(&protocol.TaskUpdate{Request: req})
}

type workerServer struct {
	protocol.UnimplementedWorkerServer
	errors chan error
}

// Receives messages until the stream fails, and reports each result.
func (s *workerServer) GetTasks(stream protocol.Worker_GetTasksServer) error {
	for {
		_, err := stream.Recv()
		s.errors <- err
		if err != nil {
			return err
		}
	}
}

// Starts a server with the options and returns a connection to it.
func serve(t *testing.T, scheduler *schedulerServer, worker *workerServer, options ...grpc.ServerOption) *grpc.ClientConn {
	server := grpc.NewServer(options...)
	protocol.RegisterSchedulerServer(server, scheduler)
	protocol.RegisterWorkerServer(server, worker)

	listener, err := net.Listen("tcp", "localhost:0")
	assert.NoError(t, err)
	go server.Serve(listener)
	t.Cleanup(server.Stop)

	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	assert.NoError(t, err)
	t.Cleanup(func() { conn.Close() })
	return conn
}

func testContext(t *testing.T) context.Context {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	t.Cleanup(cancel)
	return ctx
}

func TestUnaryRejectsInvalid(t *testing.T) {
	scheduler := &schedulerServer{}
	conn := serve(t, scheduler, &workerServer{}, pkgvalidate.ServerOptions()...)

	_, err := protocol.NewSchedulerClient(conn).CancelBuild(testContext(t), &protocol.CancelBuildRequest{})
	assert.Equal(t, codes.InvalidArgument, status.Code(err))
	assert.Empty(t, scheduler.cancelled)

	details := status.Convert(err).Details()
	if assert.Len(t, details, 1) {
		violations, ok := details[0].(*validate.Violations)
		assert.True(t, ok)
		assert.Len(t, violations.GetViolations(), 1)
	}
}

func TestUnaryPassesValid(t *testing.T) {
	scheduler := &schedulerServer{}
	conn := serve(t, scheduler, &workerServer{}, pkgvalidate.ServerOptions()...)

	_, err := protocol.NewSchedulerClient(conn).CancelBuild(testContext(t), &protocol.CancelBuildRequest{BuildId: "b"})
	assert.NoError(t, err)
	assert.Equal(t, []string{"b"}, scheduler.cancelled)
}

func TestStreamRejectsLaterMessage(t *testing.T) {
	worker := &workerServer{errors: make(chan error, 2)}
	conn := serve(t, &schedulerServer{}, worker, pkgvalidate.ServerOptions()...)

	stream, err := protocol.NewWorkerClient(conn).GetTasks(testContext(t))
	assert.NoError(t, err)
	assert.NoError(t, stream.Send(&protocol.TaskUpdate{Request: &protocol.TaskRequest{BuildId: "b"}}))
	assert.NoError(t, stream.Send(&protocol.TaskUpdate{}))

	assert.NoError(t, <-worker.errors)
	assert.Equal(t, codes.InvalidArgument, status.Code(<-worker.errors))

	_, err = stream.Recv()
	assert.Equal(t, codes.InvalidArgument, status.Code(err))
}

func TestServerStreamRequestValidated(t *testing.T) {
	conn := serve(t, &schedulerServer{}, &workerServer{}, pkgvalidate.ServerOptions()...)

	stream, err := protocol.NewSchedulerClient(conn).ScheduleBuild(testContext(t), &protocol.BuildRequest{})
	assert.NoError(t, err)
	_, err = stream.Recv()
	assert.Equal(t, codes.InvalidArgument, status.Code(err))
}

func TestAuthenticationFirst(t *testing.T) {
	authenticator, err := auth.New(auth.Config{
		Tokens: []auth.Token{{Name: "ci", Hash: auth.HashToken("ci-token"), Permissions: []auth.Permission{auth.Write}}},
	}, auth.Read, auth.Write)
	assert.NoError(t, err)

	options := authenticator.ServerOptions(func(string) auth.Permission { return auth.Write })
	options = append(options, pkgvalidate.ServerOptions()...)
	scheduler := &schedulerServer{}
	conn := serve(t, scheduler, &workerServer{}, options...)

	_, err = protocol.NewSchedulerClient(conn).CancelBuild(testContext(t), &protocol.CancelBuildRequest{})
	assert.Equal(t, codes.Unauthenticated, status.Code(err))
	assert.Empty(t, scheduler.cancelled)
}
