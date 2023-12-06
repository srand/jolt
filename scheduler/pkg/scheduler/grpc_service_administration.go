package scheduler

import (
	"context"

	"github.com/golang/protobuf/ptypes/empty"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/protobuf/types/known/emptypb"
)

type adminService struct {
	protocol.UnimplementedAdministrationServer
	scheduler Scheduler
}

func NewAdminService(scheduler Scheduler) *adminService {
	return &adminService{
		scheduler: scheduler,
	}
}

func (s *adminService) CancelBuild(_ context.Context, req *protocol.CancelBuildRequest) (*protocol.CancelBuildResponse, error) {
	panic("not implemented") // TODO: Implement
}

func (s *adminService) ListBuilds(_ context.Context, req *protocol.ListBuildsRequest) (*protocol.ListBuildsResponse, error) {
	panic("not implemented") // TODO: Implement
}

func (s *adminService) ListWorkers(_ context.Context, req *protocol.ListWorkersRequest) (*protocol.ListWorkersResponse, error) {
	panic("not implemented") // TODO: Implement
}

func (s *adminService) Reschedule(_ context.Context, _ *empty.Empty) (*empty.Empty, error) {
	s.scheduler.Reschedule()
	return &emptypb.Empty{}, nil
}
