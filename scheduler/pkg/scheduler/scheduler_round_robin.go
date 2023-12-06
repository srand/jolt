package scheduler

import (
	"context"
	"fmt"
	"sync"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type roundRobinScheduler struct {
	sync.Mutex
	rescheduleChan chan bool

	builds       map[string]*Build
	readyBuilds  map[string]*Build
	workers      map[string]Worker
	availWorkers map[string]Worker
	workerTasks  map[string]Worker
}

func NewRoundRobinScheduler() *roundRobinScheduler {
	return &roundRobinScheduler{
		rescheduleChan: make(chan bool, 10),
		builds:         map[string]*Build{},
		readyBuilds:    map[string]*Build{},
		workers:        map[string]Worker{},
		availWorkers:   map[string]Worker{},
		workerTasks:    map[string]Worker{},
	}
}

func (s *roundRobinScheduler) ScheduleBuild(build *Build) error {
	s.Lock()
	defer s.Unlock()

	if err := s.checkWorkerEligibility(build); err != nil {
		log.Info("Build was rejected, no eligible worker:", err)
		return err
	}

	log.Info("New build accepted:", build.Id())

	s.builds[build.Id()] = build
	return nil
}

func (s *roundRobinScheduler) CancelBuild(buildId string) error {
	s.Lock()
	defer s.Unlock()

	build, ok := s.builds[buildId]
	if !ok {
		log.Debug("Cannot cancel build, not found:", buildId)
		return pkg.NotFoundError
	}

	log.Info("Build cancellation request for", buildId)

	s.dequeueBuildNoLock(build)
	build.Cancel()
	s.Reschedule()
	return nil
}

func (s *roundRobinScheduler) GetBuild(buildId string) *Build {
	s.Lock()
	defer s.Unlock()

	build, _ := s.builds[buildId]
	return build
}

func (s *roundRobinScheduler) ScheduleTask(buildId, identity string) (TaskUpdateObserver, error) {
	s.Lock()
	defer s.Unlock()

	build, ok := s.builds[buildId]
	if !ok {
		log.Debug("Task requested denied, no such build:", buildId)
		return nil, pkg.NotFoundError
	}

	task, observer, err := build.ScheduleTask(identity)
	if err != nil {
		log.Debug("Failed to schedule task in build:", err)
		return nil, err
	}

	log.Debug("New task scheduled:", task.Identity(), task.Name())

	if build.HasTasks() {
		s.enqueueBuildNoLock(build)
		if s.hasReadyWorker() {
			go s.Reschedule()
		}
	}

	return observer, nil
}

func (s *roundRobinScheduler) Reschedule() {
	s.rescheduleChan <- true
}

func (s *roundRobinScheduler) Run(ctx context.Context) {
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

				log.Debugf("Schedling build %s in worker %s", task.Build().id, worker.Id())
				worker.Tasks() <- task
			}
		}
	}
}

func (s *roundRobinScheduler) cancelAllBuilds() error {
	s.Lock()
	defer s.Unlock()

	for _, build := range s.builds {
		s.dequeueBuildNoLock(build)
		build.Cancel()
	}

	return nil
}

func (s *roundRobinScheduler) cancelAllWorkers() error {
	s.Lock()
	defer s.Unlock()

	for _, worker := range s.workers {
		s.dequeueWorkerNoLock(worker)
		worker.Cancel()
	}

	return nil
}

func (s *roundRobinScheduler) checkWorkerEligibility(build *Build) error {
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

func (s *roundRobinScheduler) hasReadyWorker() bool {
	return len(s.availWorkers) > 0
}

func (s *roundRobinScheduler) selectTaskForWorkerNoLock(worker Worker, build *Build) *Task {
	return build.FindQueuedTask(func(b *Build, t *Task) bool {
		// Must not already be allocated to a worker
		if _, ok := s.workerTasks[t.Identity()]; ok {
			return false
		}
		return worker.Platform().Fulfills(t.Platform())
	})
}

func (s *roundRobinScheduler) selectTaskAndWorker() (*Task, Worker) {
	s.Lock()
	defer s.Unlock()

	if len(s.readyBuilds) == 0 {
		return nil, nil
	}

	for _, build := range s.readyBuilds {
		for _, worker := range s.availWorkers {
			if task := s.selectTaskForWorkerNoLock(worker, build); task != nil {
				s.associateTaskWithWorker(worker, task)
				s.dequeueWorkerNoLock(worker)

				if !build.HasTasks() {
					s.dequeueBuildNoLock(build)
				}

				return task, worker
			}
		}
	}

	return nil, nil
}

func (s *roundRobinScheduler) dequeueBuildNoLock(build *Build) {
	log.Trace("Removing build from ready queue:", build.id)
	delete(s.readyBuilds, build.id)
}

func (s *roundRobinScheduler) enqueueBuildNoLock(build *Build) {
	log.Trace("Moving build to ready queue:", build.id)
	s.readyBuilds[build.id] = build
}

func (s *roundRobinScheduler) dequeueWorkerNoLock(worker Worker) {
	log.Trace("Marking worker as busy:", worker.Id())
	delete(s.availWorkers, worker.Id())
}

func (s *roundRobinScheduler) enqueueWorkerNoLock(worker Worker) {
	log.Trace("Marking worker as free:", worker.Id())
	s.availWorkers[worker.Id()] = worker
}

func (s *roundRobinScheduler) associateTaskWithWorker(worker Worker, task *Task) {
	s.workerTasks[task.Identity()] = worker
}

func (s *roundRobinScheduler) deassociateTaskWithWorker(worker Worker) {
	for t, w := range s.workerTasks {
		if w == worker {
			delete(s.workerTasks, t)
			return
		}
	}
}

func (s *roundRobinScheduler) removeStaleBuilds() {
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

func (s *roundRobinScheduler) closeBuildNoLock(build *Build) {
	log.Info("Removing build", build.Id())
	s.dequeueBuildNoLock(build)
	delete(s.builds, build.Id())
	build.Close()
}

func (s *roundRobinScheduler) NewWorker(platform *Platform) (Worker, error) {
	s.Lock()
	defer s.Unlock()

	ctx, cancel := context.WithCancel(context.Background())

	id, _ := uuid.NewRandom()
	worker := &roundRobinWorker{
		ctx:       ctx,
		cancel:    cancel,
		tasks:     make(chan *Task, 1),
		id:        id,
		platform:  platform,
		scheduler: s,
	}
	s.workers[id.String()] = worker

	log.Info("New worker enlisted:", worker.Id())
	log.Info("Properties:")
	for _, prop := range worker.Platform().Properties {
		log.Infof("  %s=%s", prop.Key, prop.Value)
	}

	s.workers[worker.Id()] = worker
	s.enqueueWorkerNoLock(worker)
	go s.Reschedule()

	return worker, nil
}

func (s *roundRobinScheduler) releaseWorker(worker Worker) error {
	s.Lock()
	defer s.Unlock()
	s.deassociateTaskWithWorker(worker)
	s.enqueueWorkerNoLock(worker)
	go s.Reschedule()
	return nil
}

func (s *roundRobinScheduler) removeWorker(worker Worker) error {
	s.Lock()
	defer s.Unlock()

	log.Info("Worker delisted:", worker.Id())

	s.deassociateTaskWithWorker(worker)
	delete(s.availWorkers, worker.Id())
	delete(s.workers, worker.Id())
	go s.Reschedule()
	return nil
}

func (s *roundRobinScheduler) NewExecutor(workerid, buildid string) (Executor, error) {
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
