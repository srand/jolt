package scheduler

import (
	"errors"
	"io"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

type workerService struct {
	protocol.UnimplementedWorkerServer
	scheduler Scheduler
}

func NewWorkerService(scheduler Scheduler) *workerService {
	return &workerService{
		scheduler: scheduler,
	}
}

func (s *workerService) GetInstructions(stream protocol.Worker_GetInstructionsServer) error {
	status, err := stream.Recv()
	if err != nil {
		return err
	}

	if status.Status != protocol.WorkerUpdate_ENLISTING {
		return errors.New("bad request")
	}

	worker, err := s.scheduler.NewWorker((*Platform)(status.Platform))
	if err != nil {
		return err
	}
	defer worker.Close()

	updates := make(chan *protocol.WorkerUpdate, 1)
	go func() {
		defer close(updates)

		for {
			update, err := stream.Recv()
			if err == io.EOF {
				return
			}
			if err != nil {
				log.Trace("Worker read error", err)
				return
			}

			updates <- update
		}
	}()

	var currentBuild *Build
	var currentBuildCtx <-chan struct{}
	var currentTask *Task

	for {
		select {
		case <-currentBuildCtx:
			log.Info("Sending cancellation request to worker for", currentBuild.Id())
			currentBuildCtx = nil

			request := &protocol.WorkerRequest{
				Action:   protocol.WorkerRequest_CANCEL_BUILD,
				Build:    &protocol.BuildRequest{},
				WorkerId: worker.Id(),
				BuildId:  currentBuild.Id(),
			}

			if err := stream.Send(request); err != nil {
				log.Trace("Worker write error:", err)
				return err
			}

		case <-worker.Done():
			log.Debug("Worker cancelled")
			return nil

		case task := <-worker.Tasks():
			if task == nil {
				return nil
			}

			if currentBuild != nil {
				panic("Got a new build assignment while another build is in progress")
			}

			currentBuild = task.build
			currentBuildCtx = task.build.Done()
			currentTask = task

			request := &protocol.WorkerRequest{
				Action: protocol.WorkerRequest_BUILD,
				Build: &protocol.BuildRequest{
					Environment: currentBuild.environment,
				},
				WorkerId: worker.Id(),
				BuildId:  currentBuild.Id(),
			}

			if err := stream.Send(request); err != nil {
				log.Trace("Worker write error:", err)
				return err
			}

		case update := <-updates:
			if update == nil {
				log.Trace("Worker stream closed")
				return nil
			}

			switch update.Status {
			case protocol.WorkerUpdate_BUILD_ENDED:
				currentBuild = nil
				currentBuildCtx = nil
				currentTask = nil
				worker.Acknowledge()

			case protocol.WorkerUpdate_DEPLOY_FAILED, protocol.WorkerUpdate_EXECUTOR_FAILED:

				var errType string

				switch update.Status {
				case protocol.WorkerUpdate_DEPLOY_FAILED:
					log.Debug("Worker failed to deploy executor for build", currentBuild.Id())
					errType = "Deployment Error"

				case protocol.WorkerUpdate_EXECUTOR_FAILED:
					log.Debug("Executor failed for build", currentBuild.Id())
					errType = "Executor Error"

				default:
					log.Debug("Unspecified worker error for build", currentBuild.Id())
					errType = "Worker Error"
				}

				currentTask.PostUpdate(&protocol.TaskUpdate{
					Status: protocol.TaskStatus_TASK_ERROR,
					Request: &protocol.TaskRequest{
						BuildId: currentBuild.Id(),
						TaskId:  currentTask.Identity(),
					},
					Worker: &protocol.WorkerAllocation{
						Id: worker.Id(),
					},
					Errors: []*protocol.TaskError{
						{
							Type:     errType,
							Location: worker.Id(),
							Message:  update.Error.Message,
							Details:  update.Error.Details,
						},
					},
				})

				currentBuild.Cancel()
				currentBuild = nil
				currentBuildCtx = nil
				currentTask = nil

				// Ready to accept new work
				worker.Acknowledge()

			default:
				log.Warn("Unrecognized update received from worker:", update)
			}
		}
	}
}

func (s *workerService) GetTasks(stream protocol.Worker_GetTasksServer) error {
	// Wait for initial message about what worker and build the request is concerning
	status, err := stream.Recv()
	if err != nil {
		log.Trace("Executor read error:", err)
		return err
	}

	executor, err := s.scheduler.NewExecutor(status.Worker.Id, status.Request.BuildId)
	if err != nil {
		log.Errorf("Executor failed to enlist for build: %s - %v", status.Request.BuildId, err)
		return err
	}
	defer executor.Close()

	log.Infof("Executor enlisted for build: %s", status.Request.BuildId)

	updates := make(chan *protocol.TaskUpdate, 100)
	go func() {
		defer close(updates)
		for {
			update, err := stream.Recv()
			if err == io.EOF {
				return
			}
			if err != nil {
				log.Trace("Executor read error:", err)
				return
			}
			updates <- update
		}
	}()

	var currentTask *Task
	for {
		select {
		case <-executor.Done():
			log.Infof("Executor delisted for build: %s", status.Request.BuildId)
			return nil

		case task := <-executor.Tasks():
			if task == nil {
				return nil
			}

			if currentTask != nil {
				panic("Got a new task assignment while another task is in progress")
			}

			currentTask = task

			request := &protocol.TaskRequest{
				BuildId: currentTask.Build().id,
				TaskId:  currentTask.Identity(),
			}

			if err := stream.Send(request); err != nil {
				log.Trace("Executor write error:", err)
				return err
			}

		case update := <-updates:
			if update == nil {
				return nil
			}

			if err == io.EOF {
				return nil
			}
			if err != nil {
				log.Trace("Executor read error:", err)
				return err
			}

			if currentTask == nil {
				log.Debug("Got task update with no task in progress")
				continue
			}

			if update.Request.TaskId != currentTask.Identity() {
				log.Debug("Got task update for a task not in progress")
				continue
			}

			log.Trace("Task update", update.Request.TaskId, update.Status)
			currentTask.PostUpdate(update)

			if update.Status.IsCompleted() {
				log.Debug("Task execution finished:", update.Request.TaskId)
				executor.Acknowledge()
				currentTask = nil
			}
		}
	}
}
