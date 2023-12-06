package scheduler

import (
	"context"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type schedulerService struct {
	protocol.UnimplementedSchedulerServer
	scheduler Scheduler
}

func NewSchedulerService(scheduler Scheduler) *schedulerService {
	return &schedulerService{
		scheduler: scheduler,
	}
}

func (s *schedulerService) ScheduleBuild(context context.Context, request *protocol.BuildRequest) (*protocol.BuildResponse, error) {
	var build *Build

	id, err := utils.Sha1String(request.String())
	if err != nil {
		return nil, err
	}

	if build = s.scheduler.GetBuild(id); build == nil {
		build = NewBuildFromRequest(id, request)
	}

	if err := s.scheduler.ScheduleBuild(build); err != nil {
		return nil, err
	}

	return &protocol.BuildResponse{
		BuildId: build.id,
		Status:  build.status,
	}, nil
}

func (s *schedulerService) CancelBuild(ctx context.Context, req *protocol.CancelBuildRequest) (*protocol.CancelBuildResponse, error) {
	if err := s.scheduler.CancelBuild(req.BuildId); err != nil {
		return nil, err
	}

	return &protocol.CancelBuildResponse{
		Status: protocol.BuildStatus_BUILD_CANCELLED,
	}, nil
}

func (s *schedulerService) ScheduleTask(request *protocol.TaskRequest, stream protocol.Scheduler_ScheduleTaskServer) error {
	observer, err := s.scheduler.ScheduleTask(request.BuildId, request.TaskId)
	if err != nil {
		return err
	}
	defer observer.Close()

	for {
		select {
		case update := <-observer.Updates():
			if err := stream.Send(update); err != nil {
				return err
			}

			if update.Status.IsCompleted() {
				return nil
			}
		}
	}
}
