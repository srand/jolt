package scheduler

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func buildEventRequest() *protocol.BuildRequest {
	return &protocol.BuildRequest{Environment: &protocol.BuildEnvironment{
		Parameters: []*protocol.Property{
			{Key: "config.username", Value: "alice"},
			{Key: "config.origin", Value: "  https://ci.example/build/42\n"},
			{Key: "custom", Value: "unchanged"},
			{Key: "custom", Value: "duplicate"},
		},
		Tasks: map[string]*protocol.Task{
			"target":     {Identity: "target", Instance: "target-instance", Name: "target"},
			"dependency": {Identity: "dependency", Instance: "dependency-instance", Name: "dependency"},
		},
	}}
}

func buildSnapshot(t *testing.T, hub *EventHub, filter *EventFilter) *protocol.Snapshot {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	consumer, err := hub.Subscribe(ctx, filter)
	require.NoError(t, err)
	defer consumer.Close()
	snapshot := recv(t, consumer).GetSnapshot()
	require.NotNil(t, snapshot)
	return snapshot
}

// Compares parameter lists by value; assert.Equal also compares protobuf internals.
func assertParameters(t *testing.T, expected, actual []*protocol.Property, msgAndArgs ...interface{}) {
	t.Helper()
	assert.True(t, proto.Equal(&protocol.BuildInfo{Parameters: expected}, &protocol.BuildInfo{Parameters: actual}), msgAndArgs...)
}

func TestBuildRegistrationBeforeTasksAndInitialSnapshot(t *testing.T) {
	s := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	s.AddObserver(hub)
	consumer, err := hub.Subscribe(context.Background(), nil)
	require.NoError(t, err)
	defer consumer.Close()
	assert.Empty(t, recv(t, consumer).GetSnapshot().Builds)

	request := buildEventRequest()
	expected := proto.Clone(request.Environment).(*protocol.BuildEnvironment)
	build := s.NewBuild("build", request)
	defer build.Close()
	// Mutating the producer's request must not mutate registered metadata.
	request.Environment.Parameters[0].Value = "mutated"
	observer, err := s.ScheduleBuild(build)
	require.NoError(t, err)
	defer observer.Close()
	info := recv(t, consumer).GetBuild()
	require.NotNil(t, info)
	assert.Equal(t, "build", info.Id)
	assert.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, info.Status)
	assert.WithinDuration(t, build.ScheduledAt(), info.ScheduledAt.AsTime(), time.Nanosecond)
	assertParameters(t, expected.Parameters, info.Parameters)

	// A registered client is still submitting, even with no queued tasks.
	s.removeStaleBuilds()
	snapshot := buildSnapshot(t, hub, NewEventFilter(&protocol.StreamEventsRequest{}))
	require.Len(t, snapshot.Builds, 1)
	assert.Empty(t, snapshot.Tasks)
	assert.True(t, proto.Equal(info, snapshot.Builds[0]))
	for _, id := range []string{"dependency", "target"} {
		taskObserver, err := s.ScheduleTask(build.Id(), id)
		require.NoError(t, err)
		defer taskObserver.Close()
		task := recv(t, consumer).GetTask()
		require.NotNil(t, task)
		assert.Equal(t, build.Id(), task.BuildId)
		assert.Equal(t, id+"-instance", task.Instance)
	}
	assert.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, info.Status, "published registration must remain immutable")
}

func TestBuildCancellationSnapshotAndRemoval(t *testing.T) {
	for _, cancelKind := range []string{"rpc", "scheduler", "direct", "shutdown"} {
		t.Run(cancelKind, func(t *testing.T) {
			s := NewPriorityScheduler()
			hub, _ := newTestHub(t)
			s.AddObserver(hub)
			build := s.NewBuild("build", buildEventRequest())
			defer build.Close()
			observer, err := s.ScheduleBuild(build)
			require.NoError(t, err)
			defer observer.Close()
			<-observer.Updates() // acceptance
			consumer, err := hub.Subscribe(context.Background(), &EventFilter{Builds: true})
			require.NoError(t, err)
			defer consumer.Close()
			accepted := recv(t, consumer).GetSnapshot().Builds[0]
			cancel := func() {
				switch cancelKind {
				case "rpc":
					response, err := NewAdminService(s, hub).CancelBuild(context.Background(), &protocol.CancelBuildRequest{BuildId: build.Id()})
					require.NoError(t, err)
					assert.Equal(t, protocol.BuildStatus_BUILD_CANCELLED, response.Status)
				case "scheduler":
					require.NoError(t, s.CancelBuild(build.Id()))
				case "direct":
					build.Cancel()
				case "shutdown":
					require.NoError(t, s.cancelAllBuilds())
				}
			}
			cancel()
			cancelled := recv(t, consumer).GetBuild()
			require.NotNil(t, cancelled)
			assert.Equal(t, protocol.BuildStatus_BUILD_CANCELLED, cancelled.Status)
			assertParameters(t, accepted.Parameters, cancelled.Parameters)
			assert.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, accepted.Status)
			select {
			case update := <-observer.Updates():
				assert.Equal(t, protocol.BuildStatus_BUILD_CANCELLED, update.Status)
			case <-time.After(5 * time.Second):
				t.Fatal("client did not receive cancellation")
			}
			postSync(t, hub, cancel)
			select {
			case event := <-consumer.Chan:
				t.Fatalf("repeated cancellation emitted %v", event)
			default:
			}
			snapshot := buildSnapshot(t, hub, &EventFilter{Builds: true})
			require.Len(t, snapshot.Builds, 1, "terminal metadata survives until removal")
			assert.True(t, proto.Equal(cancelled, snapshot.Builds[0]))
			s.removeStaleBuilds()
			removed := recv(t, consumer).GetBuildRemoved()
			require.NotNil(t, removed)
			assert.Equal(t, build.Id(), removed.Id)
			assert.Empty(t, buildSnapshot(t, hub, nil).Builds)
			assertParameters(t, accepted.Parameters, cancelled.Parameters, "cleanup cannot erase published parameters")
		})
	}
}

func TestBuildCompletionAtTerminalCleanup(t *testing.T) {
	s := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	s.AddObserver(hub)
	build := s.NewBuild("build", buildEventRequest())
	defer build.Close()
	observer, err := s.ScheduleBuild(build)
	require.NoError(t, err)
	consumer, err := hub.Subscribe(context.Background(), &EventFilter{Builds: true})
	require.NoError(t, err)
	defer consumer.Close()
	accepted := recv(t, consumer).GetSnapshot().Builds[0]

	// Neither an empty queue nor a completed individual task closes a client build.
	s.removeStaleBuilds()
	assert.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, build.Status())
	taskObserver, err := s.ScheduleTask(build.Id(), "target")
	require.NoError(t, err)
	locked := build.(*priorityBuild)
	locked.tasks["target"].PostStatusUpdate(protocol.TaskStatus_TASK_PASSED)
	s.removeStaleBuilds()
	assert.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, build.Status())
	observer.Close()
	assert.False(t, build.IsTerminal(), "queued task/observer must keep build alive")
	taskObserver.Close()
	assert.False(t, build.IsTerminal(), "queued work must keep build alive without clients")

	// Acknowledge the task just as the worker executor would.
	worker, err := s.NewWorker(NewPlatformWithDefaults(), NewPlatform())
	require.NoError(t, err)
	defer worker.Close()
	locked.tasks["target"].PostStatusUpdate(protocol.TaskStatus_TASK_QUEUED)
	executor, err := locked.NewExecutor(s, worker)
	require.NoError(t, err)
	defer executor.Close()
	select {
	case <-executor.Tasks():
	case <-time.After(5 * time.Second):
		t.Fatal("executor did not receive task")
	}
	assert.False(t, build.IsTerminal(), "unacknowledged work must keep build alive")
	locked.tasks["target"].PostStatusUpdate(protocol.TaskStatus_TASK_FAILED)
	executor.Acknowledge()
	require.True(t, build.IsTerminal())

	// This is the same atomic eligibility check used by stale cleanup.
	require.True(t, locked.finishIfTerminal())
	// Direct hub subscriptions filter snapshots only; gRPC filters increments.
	var completed *protocol.BuildInfo
	for completed == nil {
		completed = recv(t, consumer).GetBuild()
	}
	assert.Equal(t, protocol.BuildStatus_BUILD_COMPLETED, completed.Status, "completion does not distinguish task outcomes")
	assertParameters(t, accepted.Parameters, completed.Parameters)
	assert.Equal(t, protocol.BuildStatus_BUILD_COMPLETED, build.Status())
	snapshot := buildSnapshot(t, hub, &EventFilter{Builds: true})
	require.Len(t, snapshot.Builds, 1)
	assert.True(t, proto.Equal(completed, snapshot.Builds[0]))
	s.removeStaleBuilds()
	require.Equal(t, build.Id(), recv(t, consumer).GetBuildRemoved().GetId())
	assert.Empty(t, buildSnapshot(t, hub, nil).Builds)
}

func TestBuildCleanupRechecksObserver(t *testing.T) {
	s := NewPriorityScheduler()
	build := s.NewBuild("build", buildEventRequest()).(*priorityBuild)
	defer build.Close()
	observer, err := s.ScheduleBuild(build)
	require.NoError(t, err)
	observer.Close()
	require.True(t, build.IsTerminal()) // candidate selected under scheduler RLock
	observer, err = s.ScheduleBuild(build)
	require.NoError(t, err)
	defer observer.Close()
	assert.False(t, build.finishIfTerminal(), "new client invalidates stale cleanup selection")
	assert.Equal(t, protocol.BuildStatus_BUILD_ACCEPTED, build.Status())
}

func TestBuildCleanupEmitsCompletionBeforeRemoval(t *testing.T) {
	s := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	s.AddObserver(hub)
	consumer, err := hub.Subscribe(context.Background(), &EventFilter{Builds: true, NoSnapshot: true})
	require.NoError(t, err)
	defer consumer.Close()
	build := s.NewBuild("build", buildEventRequest())
	defer build.Close()
	observer, err := s.ScheduleBuild(build)
	require.NoError(t, err)
	accepted := recv(t, consumer).GetBuild()
	require.NotNil(t, accepted)
	observer.Close()
	s.removeStaleBuilds()
	completed := recv(t, consumer).GetBuild()
	require.NotNil(t, completed)
	assert.Equal(t, protocol.BuildStatus_BUILD_COMPLETED, completed.Status)
	assertParameters(t, accepted.Parameters, completed.Parameters)
	assert.Equal(t, build.Id(), recv(t, consumer).GetBuildRemoved().GetId())
	assert.Empty(t, buildSnapshot(t, hub, nil).Builds)
	_, err = s.GetBuild(build.Id())
	assert.ErrorIs(t, err, utils.ErrNotFound)
}

func TestBuildEventBackpressure(t *testing.T) {
	hub, _ := newTestHub(t)
	info := &protocol.BuildInfo{Id: "build", ScheduledAt: timestamppb.Now(), Parameters: buildEventRequest().Environment.Parameters}

	// Flooding the bounded queue from a build-locked callback must not require
	// that lock in the mirror goroutine, even while subscriptions are processed.
	finished := make(chan struct{})
	go func() {
		defer close(finished)
		for range eventQueueDepth * 2 {
			hub.BuildStatusChanged(info)
		}
	}()
	select {
	case <-finished:
	case <-time.After(5 * time.Second):
		t.Fatal("hub stopped draining build updates")
	}
}

type buildEventStream struct {
	grpc.ServerStream
	ctx    context.Context
	cancel context.CancelFunc
	id     string
}

func (s *buildEventStream) Context() context.Context { return s.ctx }
func (s *buildEventStream) Send(update *protocol.BuildUpdate) error {
	s.id = update.BuildId
	s.cancel()
	return nil
}

func TestIdenticalBuildRequestsCoalesceWithOneRegistration(t *testing.T) {
	s := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	s.AddObserver(hub)
	service := NewSchedulerService(s)
	consumer, err := hub.Subscribe(context.Background(), &EventFilter{Builds: true, NoSnapshot: true})
	require.NoError(t, err)
	defer consumer.Close()
	var wg sync.WaitGroup
	ids := make(chan string, 8)
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			stream := &buildEventStream{ctx: ctx, cancel: cancel}
			assert.NoError(t, service.ScheduleBuild(buildEventRequest(), stream))
			ids <- stream.id
		}()
	}
	wg.Wait()
	close(ids)
	expected, err := utils.Blake3String(buildEventRequest().String())
	require.NoError(t, err)
	for id := range ids {
		assert.Equal(t, expected, id)
	}
	snapshot := buildSnapshot(t, hub, nil)
	require.Len(t, snapshot.Builds, 1)
	assert.Equal(t, expected, snapshot.Builds[0].Id)
	require.Equal(t, expected, recv(t, consumer).GetBuild().GetId())
	select {
	case event := <-consumer.Chan:
		t.Fatalf("coalesced build emitted duplicate registration: %v", event)
	default:
	}
	build, err := s.GetBuild(expected)
	require.NoError(t, err)
	defer build.Close()
	assert.Equal(t, "target-instance", build.(*priorityBuild).tasks["target"].Instance())
}

func TestScheduleBuildCoalescesSeparateCandidates(t *testing.T) {
	s := NewPriorityScheduler()
	first := s.NewBuild("build", buildEventRequest())
	defer first.Close()
	second := s.NewBuild("build", buildEventRequest())
	defer second.Close()
	observer, err := s.ScheduleBuild(first)
	require.NoError(t, err)
	defer observer.Close()
	other, err := s.ScheduleBuild(second)
	require.NoError(t, err)
	defer other.Close()
	registered, err := s.GetBuild("build")
	require.NoError(t, err)
	assert.Same(t, first, registered)
	assert.True(t, first.HasObserver())
	assert.False(t, second.HasObserver())
}

func TestBuildProtocolContract(t *testing.T) {
	for _, contract := range []struct {
		message proto.Message
		name    protoreflect.Name
		tag     protoreflect.FieldNumber
	}{
		{&protocol.BuildInfo{}, "id", 1}, {&protocol.BuildInfo{}, "status", 2},
		{&protocol.BuildInfo{}, "scheduled_at", 3}, {&protocol.BuildInfo{}, "parameters", 4},
		{&protocol.BuildRemoved{}, "id", 1}, {&protocol.Snapshot{}, "builds", 4},
		{&protocol.StreamEventsRequest{}, "builds", 8},
		{&protocol.SchedulerEvent{}, "build", 6}, {&protocol.SchedulerEvent{}, "build_removed", 7},
	} {
		field := contract.message.ProtoReflect().Descriptor().Fields().ByName(contract.name)
		require.NotNil(t, field)
		assert.Equal(t, contract.tag, field.Number())
	}
}
