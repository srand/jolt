package scheduler

import (
	"context"
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func identityContext(name string, anonymous bool, permissions ...auth.Permission) context.Context {
	return auth.ContextWithIdentity(context.Background(), &auth.Identity{
		Name: name, Permissions: permissions, Anonymous: anonymous,
	})
}

// Submits the build of buildEventRequest as the client in the context.
func submitBuild(t *testing.T, service *schedulerService, ctx context.Context) string {
	t.Helper()
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	stream := &buildEventStream{ctx: ctx, cancel: cancel}
	require.NoError(t, service.ScheduleBuild(buildEventRequest(), stream))
	return stream.id
}

func TestBuildOwnersAreTheClientsThatSubmittedIt(t *testing.T) {
	s := NewPriorityScheduler()
	hub, _ := newTestHub(t)
	s.AddObserver(hub)
	service := NewSchedulerService(s)

	id := submitBuild(t, service, identityContext("alice", false, BuildPermission))
	submitBuild(t, service, identityContext("bob", false, BuildPermission))
	submitBuild(t, service, identityContext("alice", false, BuildPermission))
	submitBuild(t, service, identityContext("anonymous", true, BuildPermission))

	build, err := s.GetBuild(id)
	require.NoError(t, err)
	defer build.Close()
	assert.True(t, build.IsOwner("alice"))
	assert.True(t, build.IsOwner("bob"))
	assert.False(t, build.IsOwner("anonymous"))

	snapshot := buildSnapshot(t, hub, nil)
	require.Len(t, snapshot.Builds, 1)
	assert.Equal(t, []string{"alice", "bob"}, snapshot.Builds[0].Owners)
}

func TestOnlyOwnersAndAdministratorsCancelBuilds(t *testing.T) {
	s := NewPriorityScheduler()
	service := NewSchedulerService(s)
	id := submitBuild(t, service, identityContext("alice", false, BuildPermission))
	request := &protocol.CancelBuildRequest{BuildId: id}

	for _, ctx := range []context.Context{
		identityContext("carol", false, BuildPermission),
		identityContext("anonymous", true, BuildPermission),
	} {
		_, err := service.CancelBuild(ctx, request)
		assert.Equal(t, codes.PermissionDenied, status.Code(err))
	}

	_, err := service.CancelBuild(identityContext("alice", false, BuildPermission), request)
	assert.NoError(t, err)

	// Administrators cancel any build
	other := &protocol.BuildRequest{Environment: &protocol.BuildEnvironment{Tasks: map[string]*protocol.Task{}}}
	ctx, cancel := context.WithTimeout(identityContext("alice", false, BuildPermission), 5*time.Second)
	defer cancel()
	stream := &buildEventStream{ctx: ctx, cancel: cancel}
	require.NoError(t, service.ScheduleBuild(other, stream))
	_, err = service.CancelBuild(identityContext("root", false, AdminPermission), &protocol.CancelBuildRequest{BuildId: stream.id})
	assert.NoError(t, err)
}
