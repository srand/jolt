package scheduler

import (
	"context"

	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type schedulerService struct {
	protocol.UnimplementedSchedulerServer
	scheduler Scheduler
}

type observerWithError interface {
	Err() error
}

func observerError(observer any) error {
	if observer, ok := observer.(observerWithError); ok {
		return observer.Err()
	}
	return nil
}

func NewSchedulerService(scheduler Scheduler) *schedulerService {
	return &schedulerService{
		scheduler: scheduler,
	}
}

func (s *schedulerService) ScheduleBuild(request *protocol.BuildRequest, stream protocol.Scheduler_ScheduleBuildServer) error {
	var build Build

	id, err := utils.Blake3String(request.String())
	if err != nil {
		return utils.GrpcError(err)
	}

	if build, err = s.scheduler.GetBuild(id); err != nil {
		build = s.scheduler.NewBuild(id, request)
	}

	token := auth.TokenFromContext(stream.Context())
	if token != "" {
		build.SetSchedulerToken(token)
	}
	if identity, ok := auth.IdentityFromContext(stream.Context()); ok && !identity.Anonymous {
		build.AddOwner(identity.Name)
	}

	observer, err := s.scheduler.ScheduleBuild(build)
	if err != nil {
		return utils.GrpcError(err)
	}
	defer observer.Close()

	// Identical submissions share the registered build, which may not be
	// the one created above
	if identity, ok := auth.IdentityFromContext(stream.Context()); ok && !identity.Anonymous {
		if registered, err := s.scheduler.GetBuild(id); err == nil {
			registered.AddOwner(identity.Name)
			if token != "" {
				registered.SetSchedulerToken(token)
			}
		}
	}

	for {
		select {
		case update, ok := <-observer.Updates():
			if err := observerError(observer); err != nil {
				return utils.GrpcError(err)
			}
			if !ok {
				return nil
			}
			if update == nil {
				return nil
			}

			if err := stream.Send(update); err != nil {
				return utils.GrpcError(err)
			}

			if update.Status.IsCompleted() {
				return nil
			}

		case <-stream.Context().Done():
			return nil
		}
	}
}

func (s *schedulerService) CancelBuild(ctx context.Context, req *protocol.CancelBuildRequest) (*protocol.CancelBuildResponse, error) {
	// Clients may cancel their own builds, or builds without authenticated owners
	// with explicit permission. Administrators may cancel any build.
	if identity, ok := auth.IdentityFromContext(ctx); ok && !identity.Allows(AdminPermission) {
		build, err := s.scheduler.GetBuild(req.BuildId)
		if err != nil {
			return nil, utils.GrpcError(err)
		}
		owner := !identity.Anonymous && build.IsOwner(identity.Name)
		anonymous := identity.Allows(CancelAnonymousPermission) && !build.HasOwners()
		if !owner && !anonymous {
			return nil, status.Errorf(codes.PermissionDenied, "%s may only cancel its own builds", identity.Name)
		}
	}

	if err := s.scheduler.CancelBuild(req.BuildId); err != nil {
		return nil, utils.GrpcError(err)
	}

	return &protocol.CancelBuildResponse{
		Status: protocol.BuildStatus_BUILD_CANCELLED,
	}, nil
}

func (s *schedulerService) ScheduleTask(request *protocol.TaskRequest, stream protocol.Scheduler_ScheduleTaskServer) error {
	observer, err := s.scheduler.ScheduleTask(request.BuildId, request.TaskId)
	if err != nil {
		return utils.GrpcError(err)
	}
	defer observer.Close()

	for {
		select {
		case update, ok := <-observer.Updates():
			if err := observerError(observer); err != nil {
				return utils.GrpcError(err)
			}
			if !ok {
				return nil
			}
			if update == nil {
				return nil
			}

			if err := stream.Send(update); err != nil {
				return utils.GrpcError(err)
			}

			if update.Status.IsCompleted() {
				return nil
			}

		case <-stream.Context().Done():
			return nil
		}
	}
}
