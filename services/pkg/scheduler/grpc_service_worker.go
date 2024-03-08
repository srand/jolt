package scheduler

import (
	"errors"
	"io"
	"strings"
	"time"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/logstash"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type workerService struct {
	protocol.UnimplementedWorkerServer
	logs      logstash.LogStash
	scheduler Scheduler
}

func NewWorkerService(stash logstash.LogStash, scheduler Scheduler) *workerService {
	return &workerService{
		logs:      stash,
		scheduler: scheduler,
	}
}

func (s *workerService) GetInstructions(stream protocol.Worker_GetInstructionsServer) error {
	status, err := stream.Recv()
	if err != nil {
		return utils.GrpcError(err)
	}

	if status.Status != protocol.WorkerUpdate_ENLISTING {
		return errors.New("bad request")
	}

	platform := (*Platform)(status.Platform)

	taskPlatform := (*Platform)(status.TaskPlatform)
	if taskPlatform == nil {
		taskPlatform = NewPlatform()
	}

	worker, err := s.scheduler.NewWorker(platform, taskPlatform)
	if err != nil {
		return utils.GrpcError(err)
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
			log.Infof("int - build - id: %s, worker: %s", currentBuild.Id(), worker.Id())
			currentBuildCtx = nil

			request := &protocol.WorkerRequest{
				Action:   protocol.WorkerRequest_CANCEL_BUILD,
				Build:    &protocol.BuildRequest{},
				WorkerId: worker.Id(),
				BuildId:  currentBuild.Id(),
			}

			if err := stream.Send(request); err != nil {
				log.Trace("Worker write error:", err)
				return utils.GrpcError(err)
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

			if task.build.IsDone() {
				log.Debug("Got a new build assignment for a build that is already done")
				task.Cancel()
				worker.Acknowledge()
				continue
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
				return utils.GrpcError(err)
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
					log.Debug("Worker failed to deploy executor for build", currentBuild.Id(), worker.Id())
					if update.Error != nil {
						log.Debug("Executor error:", update.Error.Message, update.Error.Details)
					}
					errType = "Deployment Error"

				case protocol.WorkerUpdate_EXECUTOR_FAILED:
					log.Debug("Executor failed for build", currentBuild.Id(), worker.Id())
					if update.Error != nil {
						log.Debug("Executor error:", update.Error.Message, update.Error.Details)
					}
					errType = "Executor Error"

				default:
					log.Debug("Unspecified worker error for build", currentBuild.Id(), worker.Id())
					if update.Error != nil {
						log.Debug("Executor error:", update.Error.Message, update.Error.Details)
					}
					errType = "Worker Error"
				}

				if currentTask.PostUpdate(&protocol.TaskUpdate{
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
				}) {
					writer, err := s.logs.Append(currentTask.Instance())
					if err == nil {
						for _, line := range strings.Split(strings.TrimSpace(update.Error.Details), "\n") {
							var level protocol.LogLevel
							switch {
							case strings.HasPrefix(line, "[  ERROR]"):
								level = protocol.LogLevel_ERROR
								line = line[10:]
							case strings.HasPrefix(line, "[WARNING]"):
								level = protocol.LogLevel_WARNING
								line = line[10:]
							case strings.HasPrefix(line, "[VERBOSE]"):
								level = protocol.LogLevel_VERBOSE
								line = line[10:]
							case strings.HasPrefix(line, "[  DEBUG]"):
								level = protocol.LogLevel_DEBUG
								line = line[10:]
							case strings.HasPrefix(line, "[   INFO]"):
								level = protocol.LogLevel_INFO
								line = line[10:]
							case strings.HasPrefix(line, "[ EXCEPT]"):
								level = protocol.LogLevel_EXCEPTION
								line = line[10:]
							case strings.HasPrefix(line, "[ STDERR]"):
								level = protocol.LogLevel_STDERR
								line = line[10:]
							case strings.HasPrefix(line, "[ STDOUT]"):
								level = protocol.LogLevel_STDOUT
								line = line[10:]
							default:
								level = protocol.LogLevel_STDOUT
							}
							writer.WriteLine(&protocol.LogLine{
								Level:   level,
								Message: line,
								Time:    timestamppb.Now(),
								Context: currentTask.Identity(),
							})
						}
						writer.Close()
					}
				}

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
	execInfo, err := stream.Recv()
	if err != nil {
		log.Trace("Executor read error:", err)
		return utils.GrpcError(err)
	}

	executor, err := s.scheduler.NewExecutor(execInfo.Worker.Id, execInfo.Request.BuildId)
	if err != nil {
		log.Errorf("err - executor - failed to enlist: %v - build_id: %s", err, execInfo.Request.BuildId)
		return utils.GrpcError(err)
	}
	defer executor.Close()

	log.Infof("new - executor - build_id: %s, worker: %s", execInfo.Request.BuildId, execInfo.Worker.Id)

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

	var currentLog logstash.LogWriter
	var currentTask *Task

	defer func() {
		if currentLog != nil {
			currentLog.Close()
		}
	}()

	// Initial timeout to wait for the scheduler to send a task.
	// If the scheduler doesn't send a task within this time, the
	// executor will exit and allow the worker to be used for other
	// builds. Most likely cause of this is that another executor
	// has already been given the task that triggered this executor.
	initTimeoutPeriod := 3 * time.Second
	initTimeout := time.After(initTimeoutPeriod)

	for {
		select {
		case <-initTimeout:
			// If no new task is received within this time, the executor will exit

			if currentTask == nil {
				log.Debugf("del - executor - build_id: %s, worker: %s", execInfo.Request.BuildId, execInfo.Worker.Id)
				return nil
			}

		case <-executor.Done():
			// If the executor is cancelled, exit

			log.Infof("del - executor - build_id: %s, worker: %s", execInfo.Request.BuildId, execInfo.Worker.Id)
			return nil

		case task := <-executor.Tasks():
			// If a new task is received, start processing it

			if task == nil {
				return nil
			}

			if currentTask != nil {
				panic("Got a new task assignment while another task is in progress")
			}

			log.Debugf("run - task - id: %s (%s), worker: %s", task.Identity(), task.Instance(), execInfo.Worker.Id)

			currentTask = task
			currentTask.SetMatchedPlatform(executor.Platform())

			currentLog, err = s.logs.Append(task.Instance())
			if err != nil {
				log.Debug("unable to append log: ", err)
			}

			request := &protocol.TaskRequest{
				BuildId: currentTask.Build().id,
				TaskId:  currentTask.Identity(),
			}

			if err := stream.Send(request); err != nil {
				log.Trace("Executor write error:", err)
				return utils.GrpcError(err)
			}

		case update := <-updates:
			// If a task update is received, process it

			if update == nil {
				return nil
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

			if currentLog != nil {
				for _, line := range update.Loglines {
					if err := currentLog.WriteLine(line); err != nil {
						log.Debug(":", err)
					}
				}
			}

			currentTask.PostUpdate(update)

			if update.Status.IsCompleted() {
				log.Debugf("end - task - id: %s, worker: %s", update.Request.TaskId, execInfo.Worker.Id)

				executor.Acknowledge()

				if currentTask != nil {
					currentTask = nil
				}

				if currentLog != nil {
					currentLog.Close()
					currentLog = nil
				}

				// Reset the initial timeout. If no new task is received within this time,
				// the executor will exit and allow the worker to be used for other builds.
				initTimeout = time.After(initTimeoutPeriod)
			}
		}
	}
}
