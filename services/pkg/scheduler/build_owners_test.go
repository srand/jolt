package scheduler

import (
	"context"
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
	assert.True(t, build.HasOwners())

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
		identityContext("carol", false, BuildPermission, CancelAnonymousPermission),
		identityContext("anonymous", true, BuildPermission, CancelAnonymousPermission),
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

func TestCancelAnonymousBuildPermission(t *testing.T) {
	for _, test := range []struct {
		name        string
		permissions []auth.Permission
		token       string
		owned       bool
		code        codes.Code
	}{
		{"anonymous allowed", []auth.Permission{BuildPermission, CancelAnonymousPermission}, "", false, codes.OK},
		{"anonymous not opted in", []auth.Permission{BuildPermission}, "", false, codes.PermissionDenied},
		{"anonymous missing build permission", []auth.Permission{CancelAnonymousPermission}, "", false, codes.Unauthenticated},
		{"authenticated allowed", []auth.Permission{BuildPermission, CancelAnonymousPermission}, "token", false, codes.OK},
		{"authenticated not opted in", []auth.Permission{BuildPermission}, "token", false, codes.PermissionDenied},
		{"authenticated missing build permission", []auth.Permission{CancelAnonymousPermission}, "token", false, codes.PermissionDenied},
		{"coalesced build protected from anonymous", []auth.Permission{BuildPermission, CancelAnonymousPermission}, "", true, codes.PermissionDenied},
		{"coalesced build protected from non-owner", []auth.Permission{BuildPermission, CancelAnonymousPermission}, "token", true, codes.PermissionDenied},
		{"administrator allowed", []auth.Permission{BuildPermission, AdminPermission}, "token", true, codes.OK},
	} {
		t.Run(test.name, func(t *testing.T) {
			s := NewPriorityScheduler()
			service := NewSchedulerService(s)
			id := submitBuild(t, service, identityContext("anonymous", true, BuildPermission))
			build, err := s.GetBuild(id)
			require.NoError(t, err)
			defer build.Close()
			assert.False(t, build.HasOwners())
			if test.owned {
				assert.Equal(t, id, submitBuild(t, service, identityContext("alice", false, BuildPermission)))
				assert.True(t, build.HasOwners())
			}

			// Exercise the real interceptor: cancel-anonymous never replaces build
			// permission, and legacy clients send no authorization metadata.
			anonymous := test.permissions
			a, err := auth.New(auth.Config{
				Anonymous: &anonymous,
				Tokens: []auth.Token{{
					Name: "bob", Hash: auth.HashToken("token"), Permissions: test.permissions,
				}},
			}, Permissions...)
			require.NoError(t, err)
			listener, err := net.Listen("tcp", "127.0.0.1:0")
			require.NoError(t, err)
			server := grpc.NewServer(a.ServerOptions(GrpcPermission)...)
			protocol.RegisterSchedulerServer(server, service)
			go server.Serve(listener)
			defer server.Stop()
			conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
			require.NoError(t, err)
			defer conn.Close()
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			if test.token != "" {
				ctx = metadata.NewOutgoingContext(ctx, metadata.Pairs("authorization", "Bearer "+test.token))
			}
			response, err := protocol.NewSchedulerClient(conn).CancelBuild(ctx, &protocol.CancelBuildRequest{BuildId: id})
			assert.Equal(t, test.code, status.Code(err))
			if test.code == codes.OK {
				require.NoError(t, err)
				assert.Equal(t, protocol.BuildStatus_BUILD_CANCELLED, response.Status)
				assert.True(t, build.IsCancelled())
			} else {
				assert.False(t, build.IsCancelled())
			}
		})
	}
}
