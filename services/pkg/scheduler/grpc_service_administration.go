package scheduler

import (
	"context"
	"errors"

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
	build, err := s.scheduler.GetBuild(req.BuildId)
	if err != nil {
		return nil, err
	}

	build.Cancel()
	return &protocol.CancelBuildResponse{Status: build.Status()}, nil
}

func (s *adminService) ListBuilds(_ context.Context, req *protocol.ListBuildsRequest) (*protocol.ListBuildsResponse, error) {
	// Not implemented
	return s.scheduler.ListBuilds(req.Tasks), nil
}

func (s *adminService) ListWorkers(_ context.Context, req *protocol.ListWorkersRequest) (*protocol.ListWorkersResponse, error) {
	// Not implemented
	return nil, errors.New("not implemented")
}

func (s *adminService) Reschedule(_ context.Context, _ *empty.Empty) (*empty.Empty, error) {
	s.scheduler.Reschedule()
	return &emptypb.Empty{}, nil
}
