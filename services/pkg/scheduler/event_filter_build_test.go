package scheduler

import (
	"context"
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
)

func TestBuildEventFilters(t *testing.T) {
	for _, request := range []*protocol.StreamEventsRequest{
		{}, {Tasks: true}, {Workers: true}, {Tasks: true, Workers: true},
		{Builds: true}, {Builds: true, Tasks: true}, {Builds: true, Workers: true},
		{Builds: true, BuildId: "build", Hostname: "ignored", Labels: []string{"ignored"}, TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_RUNNING}},
		{Builds: true, BuildId: "other"},
	} {
		t.Run(request.String(), func(t *testing.T) {
			filter := NewEventFilter(request)
			want := (!request.Tasks && !request.Workers && !request.Builds || request.Builds) && request.BuildId != "other"
			assert.Equal(t, want, filter.MatchBuild("build"))
			assert.Equal(t, want, filter.MatchEvent(&protocol.SchedulerEvent{Event: &protocol.SchedulerEvent_Build{Build: &protocol.BuildInfo{Id: "build"}}}))
			assert.Equal(t, want, filter.MatchEvent(&protocol.SchedulerEvent{Event: &protocol.SchedulerEvent_BuildRemoved{BuildRemoved: &protocol.BuildRemoved{Id: "build"}}}))
			hub, _ := newTestHub(t)
			hub.BuildScheduled(&protocol.BuildInfo{Id: "build"})
			snapshot := buildSnapshot(t, hub, filter)
			if want {
				require.Len(t, snapshot.Builds, 1)
			} else {
				assert.Empty(t, snapshot.Builds)
			}
		})
	}
	assert.True(t, (*EventFilter)(nil).MatchBuild("build"))
}

type administrationEventStream struct {
	grpc.ServerStream
	ctx    context.Context
	events chan *protocol.SchedulerEvent
}

func (s *administrationEventStream) Context() context.Context { return s.ctx }
func (s *administrationEventStream) Send(event *protocol.SchedulerEvent) error {
	select {
	case s.events <- event:
		return nil
	case <-s.ctx.Done():
		return s.ctx.Err()
	}
}

func TestAdministrationStreamsFilteredBuildsAndRemovals(t *testing.T) {
	hub, _ := newTestHub(t)
	hub.BuildScheduled(&protocol.BuildInfo{Id: "build"})
	hub.BuildScheduled(&protocol.BuildInfo{Id: "other"})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	stream := &administrationEventStream{ctx: ctx, events: make(chan *protocol.SchedulerEvent, 10)}
	finished := make(chan error, 1)
	go func() {
		finished <- NewAdminService(NewPriorityScheduler(), hub).StreamEvents(&protocol.StreamEventsRequest{
			Builds: true, BuildId: "build", Hostname: "ignored", Labels: []string{"ignored"},
			TaskStatus: []protocol.TaskStatus{protocol.TaskStatus_TASK_RUNNING},
		}, stream)
	}()
	receive := func() *protocol.SchedulerEvent {
		select {
		case event := <-stream.events:
			return event
		case <-ctx.Done():
			t.Fatal("timed out waiting for administration event")
			return nil
		}
	}
	snapshot := receive().GetSnapshot()
	require.NotNil(t, snapshot)
	require.Len(t, snapshot.Builds, 1)
	assert.Equal(t, "build", snapshot.Builds[0].Id)
	hub.TaskScheduled(newTestTask(t, "task"))
	hub.BuildStatusChanged(&protocol.BuildInfo{Id: "other", Status: protocol.BuildStatus_BUILD_CANCELLED})
	hub.BuildRemoved("other")
	hub.BuildStatusChanged(&protocol.BuildInfo{Id: "build", Status: protocol.BuildStatus_BUILD_CANCELLED})
	hub.BuildRemoved("build")
	assert.Equal(t, protocol.BuildStatus_BUILD_CANCELLED, receive().GetBuild().GetStatus())
	assert.Equal(t, "build", receive().GetBuildRemoved().GetId())
	cancel()
	select {
	case err := <-finished:
		require.NoError(t, err)
	case <-time.After(5 * time.Second):
		t.Fatal("administration stream did not stop")
	}
}
