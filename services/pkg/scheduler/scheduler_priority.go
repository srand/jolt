package scheduler

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// A priority scheduler.
// Builds are scheduled in priority order, with builds of the same priority
// being scheduled by the number of queued tasks, fewest first.
type priorityScheduler struct {
	sync.RWMutex

	// Channel used to trigger rescheduling
	rescheduleChan chan bool

	// Map of build id to build
	builds map[string]*Build

	// Map of builds which have tasks available.
	// These builds are eligible for scheduling.
	readyBuilds *utils.PriorityQueue[*Build]

	// Map of worker id to worker
	workers map[string]Worker

	// Map of workers which are available for scheduling.
	availWorkers map[string]Worker

	// Map of assigned task id to worker
	workerTasks map[string]Worker

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
		rescheduleChan: make(chan bool, 1),
		builds:         map[string]*Build{},
		readyBuilds:    utils.NewPriorityQueue[*Build](buildPriorityFunc, buildEqualityFunc),
		workers:        map[string]Worker{},
		availWorkers:   map[string]Worker{},
		workerTasks:    map[string]Worker{},
	}
}

// Compares the priority of two builds.
func buildPriorityFunc(a, b any) int {
	// Order builds by priority
	if a.(*Build).Priority() < b.(*Build).Priority() {
		return 1
	} else if a.(*Build).Priority() > b.(*Build).Priority() {
		return -1
	}

	// Then by time of scheduling, oldest first
	if a.(*Build).ScheduledAt().Before(b.(*Build).ScheduledAt()) {
		return -1
	} else if a.(*Build).ScheduledAt().After(b.(*Build).ScheduledAt()) {
		return 1
	}

	return 0
}

// Compares the equality of two builds.
func buildEqualityFunc(a, b any) bool {
	return a.(*Build).Id() == b.(*Build).Id()
}

// Schedule a build for execution.
// Tasks belonging to the build must be scheduled via the ScheduleTask method.
func (s *priorityScheduler) ScheduleBuild(build *Build) (BuildUpdateObserver, error) {
	s.Lock()
	defer s.Unlock()

	if err := s.checkWorkerEligibility(build); err != nil {
		log.Info("nok - build, no eligible worker:", err)
		return nil, err
	}

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
func (s *priorityScheduler) GetBuild(buildId string) *Build {
	s.Lock()
	defer s.Unlock()

	build := s.builds[buildId]
	return build
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

// Check if there are any workers which can execute the given build.
func (s *priorityScheduler) checkWorkerEligibility(build *Build) error {
	if len(s.workers) == 0 {
		return fmt.Errorf("There are currently no workers connected")
	}

	var badTask *Task

	if !build.WalkTasks(func(b *Build, task *Task) bool {
		for _, worker := range s.workers {
			if worker.Platform().Fulfills(task.Platform()) && task.Platform().Fulfills(worker.TaskPlatform()) {
				return true
			}
		}
		badTask = task
		return false
	}) {
		return fmt.Errorf("No eligible worker available for task %s", badTask.Name())
	}
	return nil
}

// Check if there are any workers available for scheduling.
func (s *priorityScheduler) hasReadyWorker() bool {
	return len(s.availWorkers) > 0
}

// Select a task for a worker.
func (s *priorityScheduler) selectTaskForWorkerNoLock(worker Worker, build *Build) *Task {
	if build.IsDone() {
		return nil
	}

	return build.FindQueuedTask(func(b *Build, t *Task) bool {
		// Must not be cancelled
		if t.IsCompleted() {
			return false
		}

		// Must not already be allocated to a worker
		if _, ok := s.workerTasks[t.Identity()]; ok {
			return false
		}

		return worker.Platform().Fulfills(t.Platform()) && t.Platform().Fulfills(worker.TaskPlatform())
	})
}

// Select a task and worker for scheduling.
func (s *priorityScheduler) selectTaskAndWorker() {
	start := time.Now()
	defer func() {
		log.Debug("schedule() - elapsed:", time.Since(start))
	}()

	s.RLock()
	if s.readyBuilds.Len() == 0 {
		s.RUnlock()
		return
	}

	// Copy workers
	workers := make([]Worker, 0, len(s.availWorkers))
	for _, worker := range s.availWorkers {
		workers = append(workers, worker)
	}
	s.RUnlock()

	s.Lock()
	// Order builds by priority
	s.readyBuilds.Reorder()
	s.Unlock()

	// Task worker assignments
	assignments := make(map[Worker]*Task)

	// Assign tasks to workers.
	// Workers are selected in a round-robin fashion.
	// Tasks are selected in priority order.
	for _, worker := range workers {
		s.RLock()
		candidates := make([]*Task, s.readyBuilds.Len())
		wg := sync.WaitGroup{}

		// Select tasks for worker
		for i, build := range s.readyBuilds.Items() {
			if candidates[i] != nil {
				break
			}

			wg.Add(1)
			go func(i int, build *Build) {
				defer wg.Done()
				if task := s.selectTaskForWorkerNoLock(worker, build); task != nil {
					candidates[i] = task

				}
			}(i, build)
		}

		// Wait for all tasks to be selected
		wg.Wait()
		s.RUnlock()

		s.Lock()
		// Assign the first task that was selected
		for _, task := range candidates {
			if task == nil {
				continue
			}

			// Associate task with worker
			s.associateTaskWithWorker(worker, task)
			s.dequeueWorkerNoLock(worker)

			if !task.build.HasQueuedTask() {
				s.dequeueBuildNoLock(task.build)
			}

			assignments[worker] = task
			break
		}
		s.Unlock()
	}

	// Send tasks to workers
	for worker, task := range assignments {
		log.Debugf("run - build - id: %s, worker: %s", task.Build().Id(), worker.Id())
		worker.Post(task)
	}
}

// Remove a build from the ready queue.
func (s *priorityScheduler) dequeueBuildNoLock(build *Build) {
	log.Trace("Removing build from ready queue:", build.id)
	s.readyBuilds.Remove(build)
}

// Add a build to the ready queue.
func (s *priorityScheduler) enqueueBuildNoLock(build *Build) {
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
func (s *priorityScheduler) associateTaskWithWorker(worker Worker, task *Task) {
	s.workerTasks[task.Identity()] = worker
}

// Deassociate a task with a worker.
func (s *priorityScheduler) deassociateTaskWithWorker(worker Worker) {
	for t, w := range s.workerTasks {
		if w == worker {
			delete(s.workerTasks, t)
			return
		}
	}
}

// Remove builds which are in a terminal state.
func (s *priorityScheduler) removeStaleBuilds() {

	stale := []*Build{}

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

// Close a build and remove it from the scheduler.
func (s *priorityScheduler) closeBuildNoLock(build *Build) {
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
		tasks:        make(chan *Task, 1),
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
	log.Info("      properties:")
	for prop := range *worker.Platform() {
		log.Infof("      * %s", prop)
	}
	if len(*worker.TaskPlatform()) > 0 {
		log.Info("      task properties:")
		for prop := range *worker.TaskPlatform() {
			log.Infof("      * %s", prop)
		}
	}

	s.Reschedule()

	return worker, nil
}

// Release a worker back to the scheduler after it has completed a task.
func (s *priorityScheduler) releaseWorker(worker Worker) error {
	s.Lock()
	s.deassociateTaskWithWorker(worker)
	s.enqueueWorkerNoLock(worker)
	s.Unlock()

	s.Reschedule()
	return nil
}

// Remove a worker from the scheduler.
func (s *priorityScheduler) removeWorker(worker Worker) error {
	log.Info("del - worker", worker.Id())

	s.Lock()
	s.deassociateTaskWithWorker(worker)
	delete(s.availWorkers, worker.Id())
	delete(s.workers, worker.Id())
	s.Unlock()

	s.Reschedule()
	return nil
}

// Create a new executor for a build.
func (s *priorityScheduler) NewExecutor(workerid, buildid string) (Executor, error) {
	s.RLock()

	worker, ok := s.workers[workerid]
	if !ok {
		s.RUnlock()
		return nil, utils.ErrNotFound
	}

	build, ok := s.builds[buildid]
	if !ok {
		s.RUnlock()
		return nil, utils.ErrNotFound
	}

	s.RUnlock()
	return build.NewExecutor(s, worker)
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
