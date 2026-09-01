package scheduler

import (
	"context"

	"github.com/golang/protobuf/ptypes/empty"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"
)

type adminService struct {
	protocol.UnimplementedAdministrationServer
	scheduler Scheduler
	events    *EventHub
}

func NewAdminService(scheduler Scheduler, events *EventHub) *adminService {
	return &adminService{
		scheduler: scheduler,
		events:    events,
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
	return s.scheduler.ListWorkers(), nil
}

func (s *adminService) Reschedule(_ context.Context, _ *empty.Empty) (*empty.Empty, error) {
	s.scheduler.Reschedule()
	return &emptypb.Empty{}, nil
}

func (s *adminService) StreamEvents(request *protocol.StreamEventsRequest, stream protocol.Administration_StreamEventsServer) error {
	if s.events == nil {
		return status.Error(codes.Unimplemented, "event stream is not available")
	}

	ctx := stream.Context()
	filter := NewEventFilter(request)

	consumer, err := s.events.Subscribe(ctx, filter)
	if err != nil {
		return utils.GrpcError(err)
	}
	defer consumer.Close()

	for {
		select {
		case <-ctx.Done():
			return nil

		case event, ok := <-consumer.Chan:
			if !ok {
				// The subscriber could not keep up and was disconnected.
				// It must reconnect to obtain a fresh snapshot.
				if err := consumer.Err(); err != nil {
					return utils.GrpcError(err)
				}
				return nil
			}

			if !filter.MatchEvent(event) {
				continue
			}

			if err := stream.Send(event); err != nil {
				return utils.GrpcError(err)
			}
		}
	}
}
