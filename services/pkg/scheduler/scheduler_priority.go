package scheduler

import (
	"context"
	"fmt"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type priorityUnicastCallbacks struct{}

func (c *priorityUnicastCallbacks) Select(item *Task, consumer interface{}) bool {
	worker := consumer.(Worker)

	if item.IsCompleted() {
		return false
	}

	if item.IsAssigned() {
		return false
	}

	// Check if the worker can execute the task
	return worker.Platform().Fulfills(item.Platform()) && item.Platform().Fulfills(worker.TaskPlatform())
}

func (c *priorityUnicastCallbacks) Selected(item *Task, consumer interface{}) bool {
	worker := consumer.(Worker)
	item.AssignToWorker(worker)
	return true
}

func (c *priorityUnicastCallbacks) NotSelected(item *Task, consumer interface{}) bool {
	item.AssignToWorker(nil)
	if !item.build.IsCancelled() {
		item.PostStatusUpdate(protocol.TaskStatus_TASK_QUEUED)
	}
	return true
}

// A priority scheduler.
// Builds are scheduled in priority order, with builds of the same priority
// being scheduled by the number of queued tasks, fewest first.
type priorityScheduler struct {
	mu utils.RWMutex

	// Channel used to trigger rescheduling
	rescheduleChan chan bool

	// Map of build id to build
	builds map[string]*priorityBuild

	// Map of builds which have tasks available.
	// These builds are eligible for scheduling.
	readyBuilds *utils.PriorityQueue[*priorityBuild]

	// Map of worker id to worker
	workers map[string]Worker

	// Map of workers which are available for scheduling.
	availWorkers map[string]Worker

	// Map of assigned task id to worker
	workerExecutors map[Worker]Executor

	// List of telemtry receivers
	observers []SchedulerObserver

	// Statistics
	numCompletedBuilds int64
	numFailedTasks     int64
	numSuccessfulTasks int64
	numCompletedTasks  int64
}

// Create a new round robin scheduler.
func NewPriorityScheduler() *priorityScheduler {
	return &priorityScheduler{
		mu:              utils.NewRWMutex(),
		rescheduleChan:  make(chan bool, 1),
		builds:          map[string]*priorityBuild{},
		readyBuilds:     utils.NewPriorityQueue[*priorityBuild](buildPriorityFunc, buildEqualityFunc),
		workers:         map[string]Worker{},
		availWorkers:    map[string]Worker{},
		workerExecutors: map[Worker]Executor{},
	}
}

// Compares the priority of two builds.
func buildPriorityFunc(a, b any) int {
	// Order builds by priority
	if a.(*priorityBuild).Priority() < b.(*priorityBuild).Priority() {
		return 1
	} else if a.(*priorityBuild).Priority() > b.(*priorityBuild).Priority() {
		return -1
	}

	// Then by time of scheduling, oldest first
	if a.(*priorityBuild).ScheduledAt().Before(b.(*priorityBuild).ScheduledAt()) {
		return -1
	} else if a.(*priorityBuild).ScheduledAt().After(b.(*priorityBuild).ScheduledAt()) {
		return 1
	}

	return 0
}

// Compares the equality of two builds.
func buildEqualityFunc(a, b any) bool {
	return a.(*priorityBuild).Id() == b.(*priorityBuild).Id()
}

// Register a new build with the scheduler.
func (s *priorityScheduler) NewBuild(id string, request *protocol.BuildRequest) Build {
	ctx, cancel := context.WithCancel(context.Background())

	build := &priorityBuild{
		mu:             utils.NewRWMutex(),
		ctx:            ctx,
		ctxCancel:      cancel,
		environment:    request.Environment,
		id:             id,
		priority:       int(request.Priority),
		scheduledAt:    time.Now(),
		logstream:      request.Logstream,
		status:         protocol.BuildStatus_BUILD_ACCEPTED,
		tasks:          map[string]*Task{},
		queue:          utils.NewUnicast[*Task](&priorityUnicastCallbacks{}),
		buildObservers: NewBuildUpdateObservers(),
	}

	for _, task := range request.Environment.Tasks {
		task := NewTask(build, task)
		build.tasks[task.Identity()] = task
	}

	return build
}

// Schedule a build for execution.
// Tasks belonging to the build must be scheduled via the ScheduleTask method.
func (s *priorityScheduler) ScheduleBuild(b Build) (BuildUpdateObserver, error) {
	if b == nil {
		return nil, fmt.Errorf("Invalid build")
	}

	build, ok := b.(*priorityBuild)
	if !ok {
		return nil, fmt.Errorf("Invalid build type")
	}

	s.Lock()
	defer s.Unlock()

	if build.IsDone() {
		log.Debugf("exe - task - request denied, build is done - id: %s", build.Id())
		return nil, utils.GrpcError(utils.ErrTerminalBuild)
	}

	log.Info("new - build - id:", build.Id())

	s.builds[build.Id()] = build

	// Create a new build update observer
	observer := build.NewUpdateObserver()

	// Send an initial build update that the build has been accepted
	observer.Updates() <- &protocol.BuildUpdate{
		BuildId: build.Id(),
		Status:  protocol.BuildStatus_BUILD_ACCEPTED,
	}

	return observer, nil
}

// Cancel a build.
func (s *priorityScheduler) CancelBuild(buildId string) error {
	s.Lock()
	defer s.Unlock()

	build, ok := s.builds[buildId]
	if !ok {
		log.Debug("int - build - not found - id:", buildId)
		return utils.ErrNotFound
	}

	log.Info("int - build - id:", buildId)

	s.dequeueBuildNoLock(build)
	build.Cancel()
	s.Reschedule()
	return nil
}

// Returns the build with the given id, or nil.
func (s *priorityScheduler) GetBuild(buildId string) (Build, error) {
	s.Lock()
	defer s.Unlock()

	build, ok := s.builds[buildId]
	if !ok {
		return nil, utils.ErrNotFound
	}
	return build, nil
}

// Schedule a task belonging to a build for execution
func (s *priorityScheduler) ScheduleTask(buildId, identity string) (TaskUpdateObserver, error) {
	s.Lock()
	defer s.Unlock()

	build, ok := s.builds[buildId]
	if !ok {
		log.Debug("exe - task - request denied, no such build:", buildId)
		return nil, utils.ErrNotFound
	}

	if build.IsDone() {
		log.Debugf("exe - task - request denied, build is done - id: %s", buildId)
		return nil, utils.GrpcError(utils.ErrTerminalBuild)
	}

	task, observer, err := build.ScheduleTask(identity)
	if err != nil {
		log.Debug("exe - task - failed to schedule task in build:", err)
		return nil, err
	}

	// Install telemetry callbacks
	task.SetScheduler(s)

	// Post scheduling telemetry to observers
	s.TaskScheduled(task)

	log.Debugf("exe - task - id: %s, name: %s", task.Identity(), task.Name())

	if build.HasQueuedTask() {
		s.enqueueBuildNoLock(build)
		if s.hasReadyWorker() {
			s.Reschedule()
		}
	}

	return observer, nil
}

// Request scheduler to reevaluate the scheduling of builds.
func (s *priorityScheduler) Reschedule() {
	select {
	case s.rescheduleChan <- true:
	default:
	}
}

// Run the scheduler.
func (s *priorityScheduler) Run(ctx context.Context) {
	// Create a timer to trigger rescheduling in case of no activity
	tickerPeriod := time.Minute
	ticker := time.NewTicker(tickerPeriod)
	defer ticker.Stop()

	log.Info("starting")
	for {
		select {
		case <-ctx.Done():
			s.cancelAllBuilds()
			s.cancelAllWorkers()
			return

		case <-ticker.C:
			s.Reschedule()

		case <-s.rescheduleChan:
			log.Trace("rescheduling")
			ticker.Reset(tickerPeriod)
			s.removeStaleBuilds()
			s.requeueReadyBuilds()
			s.selectTaskAndWorker()
		}
	}
}

// Cancel all builds.
func (s *priorityScheduler) cancelAllBuilds() error {
	s.Lock()
	defer s.Unlock()

	for _, build := range s.builds {
		s.dequeueBuildNoLock(build)
		build.Cancel()
	}

	return nil
}

// Cancel all workers.
func (s *priorityScheduler) cancelAllWorkers() error {
	s.Lock()
	defer s.Unlock()

	for _, worker := range s.workers {
		s.dequeueWorkerNoLock(worker)
		worker.Cancel()
	}

	return nil
}

// Check if there are any workers available for scheduling.
func (s *priorityScheduler) hasReadyWorker() bool {
	return len(s.availWorkers) > 0
}

// Select a task and worker for scheduling.
func (s *priorityScheduler) selectTaskAndWorker() {
	start := time.Now()
	defer func() {
		log.Debug("schedule() - elapsed:", time.Since(start))
	}()

	s.Lock()
	// Order builds by priority
	s.readyBuilds.Reorder()
	s.Unlock()

	s.RLock()
	if s.readyBuilds.Len() == 0 {
		s.RUnlock()
		return
	}

	type assignment struct {
		build    *priorityBuild
		executor Executor
		worker   Worker
	}

	var assignments []assignment = make([]assignment, 0)

	// Assign tasks to workers.
	// Workers are selected in a round-robin fashion.
	// Tasks are selected in priority order.
	for _, worker := range s.availWorkers {
		// Select tasks for worker
		for _, build := range s.readyBuilds.Items() {
			executor, err := build.NewExecutor(s, worker)
			if err != nil {
				continue
			}

			assignments = append(assignments, assignment{
				build:    build,
				executor: &priorityExecutor{scheduler: s, executor: executor},
				worker:   worker,
			})

			break
		}
	}
	s.RUnlock()

	s.Lock()
	defer s.Unlock()

	// Send builds to workers
	for _, assign := range assignments {
		if !assign.build.HasQueuedTask() {
			s.dequeueBuildNoLock(assign.build)
		}
		s.dequeueWorkerNoLock(assign.worker)
		s.associateExecutorWithWorker(assign.worker, assign.executor)
		assign.worker.Post(assign.build)
		log.Debugf("run - build - id: %s, worker: %s", assign.build.Id(), assign.worker.Id())
	}
}

// Remove a build from the ready queue.
func (s *priorityScheduler) dequeueBuildNoLock(build *priorityBuild) {
	log.Trace("Removing build from ready queue:", build.id)
	s.readyBuilds.Remove(build)
}

// Add a build to the ready queue.
func (s *priorityScheduler) enqueueBuildNoLock(build *priorityBuild) {
	log.Trace("Moving build to ready queue:", build.id)
	s.readyBuilds.Push(build)
}

// Remove a worker from the available worker list.
func (s *priorityScheduler) dequeueWorkerNoLock(worker Worker) {
	log.Trace("Marking worker as busy:", worker.Id())
	delete(s.availWorkers, worker.Id())
}

// Add a worker to the available worker list.
func (s *priorityScheduler) enqueueWorkerNoLock(worker Worker) {
	log.Trace("Marking worker as free:", worker.Id())
	s.availWorkers[worker.Id()] = worker
}

// Associate a task with a worker.
func (s *priorityScheduler) associateExecutorWithWorker(worker Worker, executor Executor) {
	s.workerExecutors[worker] = executor
}

// Deassociate a task with a worker.
func (s *priorityScheduler) deassociateExecutorWithWorker(worker Worker) {
	s.RLock()
	executor, ok := s.workerExecutors[worker]
	s.RUnlock()

	if ok {
		executor.Close()

		s.Lock()
		delete(s.workerExecutors, worker)
		s.Unlock()
	}
}

// Remove builds which are in a terminal state.
func (s *priorityScheduler) removeStaleBuilds() {

	stale := []*priorityBuild{}

	s.RLock()
	for _, build := range s.builds {
		if build.IsTerminal() {
			stale = append(stale, build)
		}
	}
	s.RUnlock()

	s.Lock()
	for _, build := range stale {
		s.closeBuildNoLock(build)
	}
	s.Unlock()
}

// Requeue builds which are ready for scheduling.
func (s *priorityScheduler) requeueReadyBuilds() {
	s.Lock()
	for _, build := range s.builds {
		if build.HasQueuedTask() && !s.readyBuilds.Contains(build) {
			s.enqueueBuildNoLock(build)
		}
	}
	s.Unlock()
}

// Close a build and remove it from the scheduler.
func (s *priorityScheduler) closeBuildNoLock(build *priorityBuild) {
	log.Infof("del - build - id: %s", build.Id())
	s.dequeueBuildNoLock(build)
	delete(s.builds, build.Id())
	build.Close()

	// Update statistics
	atomic.AddInt64(&s.numCompletedBuilds, 1)
}

// Register a new worker with the scheduler.
func (s *priorityScheduler) NewWorker(platform, taskPlatform *Platform) (Worker, error) {

	ctx, cancel := context.WithCancel(context.Background())

	id, _ := uuid.NewRandom()
	worker := &priorityWorker{
		ctx:          ctx,
		cancel:       cancel,
		builds:       make(chan Build, 1),
		id:           id,
		platform:     platform,
		taskPlatform: taskPlatform,
		scheduler:    s,
	}

	s.Lock()
	s.workers[worker.Id()] = worker
	s.enqueueWorkerNoLock(worker)
	s.Unlock()

	// FIXME: Log as single record to avoid interleaving
	log.Info("new - worker", worker.Id())
	worker.Platform().Log("Platform", 2)
	if len(*worker.TaskPlatform()) > 0 {
		worker.TaskPlatform().Log("Task Platform", 2)
	}

	s.Reschedule()

	return worker, nil
}

// Release a worker back to the scheduler after it has completed a task.
func (s *priorityScheduler) releaseWorker(worker Worker) error {
	s.deassociateExecutorWithWorker(worker)

	s.Lock()
	s.enqueueWorkerNoLock(worker)
	s.Unlock()

	s.Reschedule()
	return nil
}

// Remove a worker from the scheduler.
func (s *priorityScheduler) removeWorker(worker Worker) error {
	log.Info("del - worker", worker.Id())

	s.deassociateExecutorWithWorker(worker)

	s.Lock()
	delete(s.availWorkers, worker.Id())
	delete(s.workers, worker.Id())
	s.Unlock()

	s.Reschedule()
	return nil
}

// Create a new executor for a build.
func (s *priorityScheduler) NewExecutor(workerid, buildid string) (Executor, error) {
	s.Lock()
	defer s.Unlock()

	worker, ok := s.workers[workerid]
	if !ok {
		return nil, utils.ErrNotFound
	}

	executor, ok := s.workerExecutors[worker]
	if !ok {
		return nil, utils.ErrNotFound
	}

	delete(s.workerExecutors, worker)
	return executor, nil
}

func (s *priorityScheduler) AddObserver(receiver SchedulerObserver) {
	s.Lock()
	defer s.Unlock()

	s.observers = append(s.observers, receiver)
}

// Implementation of SchedulerObserver interface
func (s *priorityScheduler) TaskScheduled(task *Task) {
	for _, receiver := range s.observers {
		receiver.TaskScheduled(task)
	}
}

// Implementation of SchedulerObserver interface
func (s *priorityScheduler) TaskStatusChanged(task *Task, status protocol.TaskStatus) {
	switch status {
	case protocol.TaskStatus_TASK_FAILED, protocol.TaskStatus_TASK_ERROR, protocol.TaskStatus_TASK_UNSTABLE:
		atomic.AddInt64(&s.numFailedTasks, 1)
		atomic.AddInt64(&s.numCompletedTasks, 1)
	case protocol.TaskStatus_TASK_PASSED, protocol.TaskStatus_TASK_SKIPPED, protocol.TaskStatus_TASK_UPLOADED, protocol.TaskStatus_TASK_DOWNLOADED:
		atomic.AddInt64(&s.numSuccessfulTasks, 1)
		atomic.AddInt64(&s.numCompletedTasks, 1)
	case protocol.TaskStatus_TASK_QUEUED:
		// Executor likely closed and task returned to queue
		s.Reschedule()
	}

	// Post scheduling telemetry to observers
	for _, receiver := range s.observers {
		receiver.TaskStatusChanged(task, status)
	}
}

// Scheduler statistics
func (s *priorityScheduler) Statistics() *SchedulerStatistics {
	s.RLock()
	defer s.RUnlock()

	stats := &SchedulerStatistics{
		Workers:         int64(len(s.workers)),
		Builds:          int64(len(s.builds)),
		CompletedBuilds: s.numCompletedBuilds,
		QueuedTasks:     0,
		RunningTasks:    0,
		FailedTasks:     s.numFailedTasks,
		SuccessfulTasks: s.numSuccessfulTasks,
		CompletedTasks:  s.numCompletedTasks,
	}

	for _, build := range s.builds {
		if build.IsDone() {
			stats.CompletedBuilds++
		} else {
			stats.QueuedTasks += int64(build.NumQueuedTasks())
			stats.RunningTasks += int64(build.NumRunningTasks())
		}
	}

	return stats
}

// Get information about running builds
func (s *priorityScheduler) ListBuilds(tasks bool) *protocol.ListBuildsResponse {
	s.RLock()
	defer s.RUnlock()

	response := &protocol.ListBuildsResponse{
		Builds: make([]*protocol.ListBuildsResponse_Build, 0, len(s.builds)),
	}

	for _, build := range s.builds {
		response.Builds = append(response.Builds, &protocol.ListBuildsResponse_Build{
			Id:             build.Id(),
			ScheduledAt:    timestamppb.New(build.scheduledAt),
			Status:         build.Status(),
			Tasks:          make([]*protocol.ListBuildsResponse_Task, 0, len(build.tasks)),
			HasObserver:    build.HasObserver(),
			HasRunningTask: build.HasRunningTask(),
			HasQueuedTask:  build.HasQueuedTask(),
			Ready:          s.readyBuilds.Contains(build),
		})

		if !tasks {
			continue
		}

		for _, task := range build.tasks {
			response.Builds[len(response.Builds)-1].Tasks = append(response.Builds[len(response.Builds)-1].Tasks, &protocol.ListBuildsResponse_Task{
				Id:          task.Identity(),
				Name:        task.Name(),
				Status:      task.Status(),
				HasObserver: task.HasObserver(),
			})
		}
	}

	return response
}

// Get information about connected workers.
func (s *priorityScheduler) ListWorkers() *protocol.ListWorkersResponse {
	s.RLock()
	defer s.RUnlock()

	response := &protocol.ListWorkersResponse{
		Workers: make([]*protocol.ListWorkersResponse_Worker, 0, len(s.workers)),
	}

	for _, worker := range s.workers {
		response.Workers = append(response.Workers, &protocol.ListWorkersResponse_Worker{
			Id:           worker.Id(),
			Platform:     worker.Platform().Protobuf(),
			TaskPlatform: worker.TaskPlatform().Protobuf(),
			Task:         nil,
		})

		// Get task
		executor := s.workerExecutors[worker]
		if executor == nil {
			continue
		}

		task := executor.Unacknowledged()
		if task == nil {
			continue
		}

		response.Workers[len(response.Workers)-1].Task = &protocol.ListWorkersResponse_Task{
			Id:     task.Identity(),
			Name:   task.Name(),
			Status: task.Status(),
		}
	}

	return response
}

func (s *priorityScheduler) Lock() {
	s.mu.Lock()
}

func (s *priorityScheduler) Unlock() {
	s.mu.Unlock()
}

func (s *priorityScheduler) RLock() {
	s.mu.RLock()
}

func (s *priorityScheduler) RUnlock() {
	s.mu.RUnlock()
}
