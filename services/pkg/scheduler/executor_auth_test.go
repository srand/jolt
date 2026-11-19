package scheduler

import (
	"context"
	"io"
	"net"
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func TestBuildSchedulerTokenIsPrivateAndRefreshed(t *testing.T) {
	s := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	s.AddObserver(hub)
	service := NewSchedulerService(s)
	var id string
	for _, token := range []string{"first-token", "refreshed-token", ""} {
		ctx := identityContext("alice", token == "", BuildPermission)
		ctx = metadata.NewIncomingContext(ctx, metadata.Pairs("authorization", "Bearer "+token))
		got := submitBuild(t, service, ctx)
		if id == "" {
			id = got
		}
		assert.Equal(t, id, got)
		build, err := s.GetBuild(id)
		require.NoError(t, err)
		if token != "" {
			assert.Equal(t, token, build.SchedulerToken())
		} else {
			assert.Equal(t, "refreshed-token", build.SchedulerToken())
		}
		assert.NotContains(t, build.Environment().String(), "token")
		assert.NotContains(t, buildSnapshot(t, hub, nil).String(), "token")
	}
}

type authExecutorScheduler struct {
	Scheduler
	build Build
}

func (s *authExecutorScheduler) GetBuild(string) (Build, error) { return s.build, nil }
func (s *authExecutorScheduler) NewExecutor(string, string) (Executor, error) {
	return &idleExecutor{}, nil
}

func TestGetTasksRequiresBuildPermissionAndOwnership(t *testing.T) {
	s := NewPriorityScheduler()
	build := s.NewBuild("build", buildEventRequest())
	defer build.Close()
	build.AddOwner("alice")
	a, err := auth.New(auth.Config{Tokens: []auth.Token{
		{Name: "alice", Hash: auth.HashToken("alice-token"), Permissions: []auth.Permission{BuildPermission}},
		{Name: "bob", Hash: auth.HashToken("bob-token"), Permissions: []auth.Permission{BuildPermission}},
		{Name: "worker", Hash: auth.HashToken("worker-token"), Permissions: []auth.Permission{WorkerPermission}},
	}}, Permissions...)
	require.NoError(t, err)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	server := grpc.NewServer(a.ServerOptions(GrpcPermission)...)
	protocol.RegisterWorkerServer(server, NewWorkerService(nil, &authExecutorScheduler{build: build}))
	go server.Serve(listener)
	defer server.Stop()
	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	require.NoError(t, err)
	defer conn.Close()
	for _, test := range []struct {
		token string
		code  codes.Code
	}{
		{"alice-token", codes.OK},
		{"bob-token", codes.PermissionDenied},
		{"worker-token", codes.PermissionDenied},
		{"", codes.Unauthenticated},
	} {
		t.Run(test.token, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			ctx = metadata.NewOutgoingContext(ctx, metadata.Pairs("authorization", "Bearer "+test.token))
			stream, err := protocol.NewWorkerClient(conn).GetTasks(ctx)
			require.NoError(t, err)
			_ = stream.Send(&protocol.TaskUpdate{Request: &protocol.TaskRequest{BuildId: "build"}, Worker: &protocol.WorkerAllocation{Id: "worker"}})
			_ = stream.CloseSend()
			_, err = stream.Recv()
			if test.code == codes.OK {
				assert.ErrorIs(t, err, io.EOF)
			} else {
				assert.Equal(t, test.code, status.Code(err))
			}
		})
	}
}

type assignedWorker struct {
	Worker
	builds chan Build
}

func (w *assignedWorker) Id() string            { return "worker" }
func (w *assignedWorker) Close()                {}
func (w *assignedWorker) Done() <-chan struct{} { return nil }
func (w *assignedWorker) Builds() chan Build    { return w.builds }

type assignedScheduler struct {
	Scheduler
	worker Worker
}

func (s *assignedScheduler) NewWorker(*Platform, *Platform) (Worker, error) { return s.worker, nil }

type instructionStream struct {
	grpc.ServerStream
	ctx     context.Context
	cancel  context.CancelFunc
	request *protocol.WorkerRequest
}

func (s *instructionStream) Context() context.Context { return s.ctx }
func (s *instructionStream) Recv() (*protocol.WorkerUpdate, error) {
	if s.ctx == nil {
		s.ctx, s.cancel = context.WithCancel(context.Background())
		return &protocol.WorkerUpdate{Status: protocol.WorkerUpdate_ENLISTING}, nil
	}
	<-s.ctx.Done()
	return nil, io.EOF
}
func (s *instructionStream) Send(request *protocol.WorkerRequest) error {
	s.request = request
	s.cancel()
	return io.EOF
}

func TestGetInstructionsForwardsBuildToken(t *testing.T) {
	s := NewPriorityScheduler()
	build := s.NewBuild("build", buildEventRequest())
	defer build.Close()
	build.SetSchedulerToken("submitter-token")
	w := &assignedWorker{builds: make(chan Build, 1)}
	w.builds <- build
	stream := &instructionStream{}
	_ = NewWorkerService(nil, &assignedScheduler{worker: w}).GetInstructions(stream)
	require.NotNil(t, stream.request)
	assert.Equal(t, "submitter-token", stream.request.SchedulerToken)
	assert.Equal(t, "build", stream.request.BuildId)
}
