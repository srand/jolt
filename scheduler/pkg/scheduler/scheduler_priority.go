package scheduler

import (
	"context"
	"fmt"
	"sync"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// A priority scheduler.
// Builds are scheduled in priority order, with builds of the same priority
// being scheduled by the number of queued tasks, fewest first.
type priorityScheduler struct {
	sync.Mutex

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
}

// Create a new round robin scheduler.
func NewPriorityScheduler() *priorityScheduler {
	return &priorityScheduler{
		rescheduleChan: make(chan bool, 10),
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

	// Then by the number of queued tasks. Fewer tasks is higher priority.
	if a.(*Build).NumQueuedTasks() < b.(*Build).NumQueuedTasks() {
		return 1
	} else if a.(*Build).NumQueuedTasks() > b.(*Build).NumQueuedTasks() {
		return -1
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
		return utils.NotFoundError
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

	build, _ := s.builds[buildId]
	return build
}

// Schedule a task belonging to a build for execution
func (s *priorityScheduler) ScheduleTask(buildId, identity string) (TaskUpdateObserver, error) {
	s.Lock()
	defer s.Unlock()

	build, ok := s.builds[buildId]
	if !ok {
		log.Debug("exe - task - request denied, no such build:", buildId)
		return nil, utils.NotFoundError
	}

	task, observer, err := build.ScheduleTask(identity)
	if err != nil {
		log.Debug("exe - task - failed to schedule task in build:", err)
		return nil, err
	}

	log.Debug("exe - task -", task.Identity(), task.Name())

	if build.HasQueuedTask() {
		s.enqueueBuildNoLock(build)
		if s.hasReadyWorker() {
			go s.Reschedule()
		}
	}

	return observer, nil
}

// Request scheduler to reevaluate the scheduling of builds.
func (s *priorityScheduler) Reschedule() {
	s.rescheduleChan <- true
}

// Run the scheduler.
func (s *priorityScheduler) Run(ctx context.Context) {
	log.Info("Starting")
	for {
		select {
		case <-ctx.Done():
			s.cancelAllBuilds()
			s.cancelAllWorkers()
			return

		case <-s.rescheduleChan:
			log.Trace("Rescheduling")

			for {
				s.removeStaleBuilds()

				task, worker := s.selectTaskAndWorker()
				if task == nil {
					break
				}

				log.Debugf("run - build - id: %s, worker: %s", task.Build().Id(), worker.Id())
				worker.Tasks() <- task
			}
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
			if worker.Platform().Fulfills(task.Platform()) {
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
	return build.FindQueuedTask(func(b *Build, t *Task) bool {
		// Must not already be allocated to a worker
		if _, ok := s.workerTasks[t.Identity()]; ok {
			return false
		}
		return worker.Platform().Fulfills(t.Platform())
	})
}

// Select a task and worker for scheduling.
func (s *priorityScheduler) selectTaskAndWorker() (*Task, Worker) {
	s.Lock()
	defer s.Unlock()

	if s.readyBuilds.Len() == 0 {
		return nil, nil
	}

	s.readyBuilds.Reorder()

	for _, build := range s.readyBuilds.Items() {
		for _, worker := range s.availWorkers {
			if task := s.selectTaskForWorkerNoLock(worker, build); task != nil {
				s.associateTaskWithWorker(worker, task)
				s.dequeueWorkerNoLock(worker)

				if !build.HasQueuedTask() {
					s.dequeueBuildNoLock(build)
				}

				return task, worker
			}
		}
	}

	return nil, nil
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
	s.Lock()
	defer s.Unlock()

	stale := []*Build{}

	for _, build := range s.builds {
		if build.IsTerminal() {
			stale = append(stale, build)
		}
	}

	for _, build := range stale {
		s.closeBuildNoLock(build)
	}
}

// Close a build and remove it from the scheduler.
func (s *priorityScheduler) closeBuildNoLock(build *Build) {
	log.Infof("del - build - id: %s", build.Id())
	s.dequeueBuildNoLock(build)
	delete(s.builds, build.Id())
	build.Close()
}

// Register a new worker with the scheduler.
func (s *priorityScheduler) NewWorker(platform *Platform) (Worker, error) {
	s.Lock()
	defer s.Unlock()

	ctx, cancel := context.WithCancel(context.Background())

	id, _ := uuid.NewRandom()
	worker := &priorityWorker{
		ctx:       ctx,
		cancel:    cancel,
		tasks:     make(chan *Task, 1),
		id:        id,
		platform:  platform,
		scheduler: s,
	}
	s.workers[id.String()] = worker

	// FIXME: Log as single record to avoid interleaving
	log.Info("new - worker", worker.Id())
	log.Info("      properties:")
	for _, prop := range worker.Platform().Properties {
		log.Infof("      * %s=%s", prop.Key, prop.Value)
	}

	s.workers[worker.Id()] = worker
	s.enqueueWorkerNoLock(worker)
	go s.Reschedule()

	return worker, nil
}

// Release a worker back to the scheduler after it has completed a task.
func (s *priorityScheduler) releaseWorker(worker Worker) error {
	s.Lock()
	defer s.Unlock()
	s.deassociateTaskWithWorker(worker)
	s.enqueueWorkerNoLock(worker)
	go s.Reschedule()
	return nil
}

// Remove a worker from the scheduler.
func (s *priorityScheduler) removeWorker(worker Worker) error {
	s.Lock()
	defer s.Unlock()

	log.Info("del - worker", worker.Id())

	s.deassociateTaskWithWorker(worker)
	delete(s.availWorkers, worker.Id())
	delete(s.workers, worker.Id())
	go s.Reschedule()
	return nil
}

// Create a new executor for a build.
func (s *priorityScheduler) NewExecutor(workerid, buildid string) (Executor, error) {
	s.Lock()
	defer s.Unlock()

	worker, ok := s.workers[workerid]
	if !ok {
		return nil, utils.NotFoundError
	}

	build, ok := s.builds[buildid]
	if !ok {
		return nil, utils.NotFoundError
	}

	return build.NewExecutor(s, worker.Platform())
}
