package scheduler

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/suite"
)

type SchedulerTest struct {
	suite.Suite
	createScheduler func() Scheduler
	scheduler       Scheduler
	ctx             context.Context
	cancel          func()
}

func (suite *SchedulerTest) SetupTest() {
	suite.scheduler = suite.createScheduler()
	suite.ctx, suite.cancel = context.WithCancel(context.Background())
	go suite.scheduler.Run(suite.ctx)
}

func (suite *SchedulerTest) TeardownTest() {
	suite.cancel()
}

func newBuild() *Build {
	request := protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{
			Tasks: map[string]*protocol.Task{},
		},
	}
	uid, _ := uuid.NewRandom()
	id, _ := utils.Sha1String(uid.String())
	return NewBuildFromRequest(id, &request)
}

func addTask(build *Build, name string, properties ...string) *Task {
	id, _ := uuid.NewRandom()
	instance, _ := uuid.NewRandom()

	platform := &protocol.Platform{}
	for _, prop := range properties {
		key, value, _ := strings.Cut(prop, "=")
		platform.Properties = append(platform.Properties, &protocol.Property{
			Key:   key,
			Value: value,
		})
	}

	taskRequest := protocol.Task{
		Name:     name,
		Identity: id.String(),
		Instance: instance.String(),
		Platform: platform,
	}

	task := NewTask(build, &taskRequest)
	build.tasks[task.Identity()] = task
	return task
}

func (suite *SchedulerTest) newWorker(properties ...string) (Worker, error) {
	platform := NewPlatformWithDefaults()
	for _, prop := range properties {
		key, value, _ := strings.Cut(prop, "=")
		platform.Properties = append(platform.Properties, &protocol.Property{
			Key:   key,
			Value: value,
		})
	}

	return suite.scheduler.NewWorker(platform)
}

func (suite *SchedulerTest) TestCancelScheduler() {
	build := newBuild()
	addTask(build, "task")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)

	observer, err := suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
	defer observer.Close()

	executor, err := suite.scheduler.NewExecutor(worker.Id(), build.Id())
	assert.NoError(suite.T(), err)

	suite.cancel()

	// Build should have been cancelled
	<-build.Done()
	build.Close()

	// Worker should have been cancelled
	<-worker.Done()
	worker.Close()

	// Executor should have been cancelled
	<-executor.Done()
	executor.Close()
}

func (suite *SchedulerTest) TestScheduleBuildWhileNoWorkerConnected() {
	build := newBuild()

	observer, err := suite.scheduler.ScheduleBuild(build)
	assert.Nil(suite.T(), observer)
	assert.Error(suite.T(), err)
}

func (suite *SchedulerTest) TestScheduleBuildWithNoEligibleWorker() {
	build := newBuild()
	addTask(build, "task", "label=label")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	defer worker.Close()

	observer, err := suite.scheduler.ScheduleBuild(build)
	assert.Nil(suite.T(), observer)
	assert.Error(suite.T(), err)
}

func (suite *SchedulerTest) TestScheduleBuildWithOneWorker() {
	build := newBuild()
	addTask(build, "task")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	defer worker.Close()

	observer, err := suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
	defer observer.Close()
}

func (suite *SchedulerTest) TestScheduleBuildWithEligibleWorker() {
	build := newBuild()
	addTask(build, "task", "label=one")

	worker, err := suite.newWorker("label=one")
	assert.NoError(suite.T(), err)
	defer worker.Close()

	observer, err := suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
	defer observer.Close()
}

func (suite *SchedulerTest) TestScheduleTask() {
	build := newBuild()
	task1 := addTask(build, "task11")
	task2 := addTask(build, "task21")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)

	buildObserver, err := suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
	defer buildObserver.Close()

	observer, err := suite.scheduler.ScheduleTask(build.Id(), task1.task.Identity)
	assert.NoError(suite.T(), err)
	defer observer.Close()

	scheduledTask := <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)

	executor, err := suite.scheduler.NewExecutor(worker.Id(), task1.Build().Id())
	assert.NoError(suite.T(), err)

	scheduledTask = <-executor.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)

	observer, err = suite.scheduler.ScheduleTask(build.Id(), task2.task.Identity)
	assert.NoError(suite.T(), err)
	defer observer.Close()
	executor.Acknowledge()

	scheduledTask = <-executor.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task2, scheduledTask)
	executor.Acknowledge()

	executor.Close()
	scheduledTask = <-executor.Tasks()
	assert.Nil(suite.T(), scheduledTask)

	worker.Close()
	scheduledTask = <-worker.Tasks()
	assert.Nil(suite.T(), scheduledTask)
}

func (suite *SchedulerTest) TestScheduleTaskWithRestartDueToWorkerFailure() {
	build := newBuild()
	task1 := addTask(build, "task12")
	addTask(build, "task22")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	assert.NotNil(suite.T(), worker)

	buildObserver, err := suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
	defer buildObserver.Close()

	observer, err := suite.scheduler.ScheduleTask(build.Id(), task1.task.Identity)
	assert.NoError(suite.T(), err)
	defer observer.Close()

	scheduledTask := <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)

	executor, err := suite.scheduler.NewExecutor(worker.Id(), task1.Build().Id())
	assert.NoError(suite.T(), err)

	scheduledTask = <-executor.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)

	// Simulate disconnection
	executor.Close()
	worker.Close()

	worker, err = suite.newWorker()
	assert.NoError(suite.T(), err)
	assert.NotNil(suite.T(), worker)

	scheduledTask = <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)

	worker.Close()
}

func (suite *SchedulerTest) TestScheduleTaskWithInvalidIdentifiers() {
	build := newBuild()
	task := addTask(build, "task")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	defer worker.Close()

	buildObserver, err := suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
	defer buildObserver.Close()

	observer, err := suite.scheduler.ScheduleTask("bad build", task.task.Identity)
	assert.Error(suite.T(), err)
	assert.Nil(suite.T(), observer)

	observer, err = suite.scheduler.ScheduleTask(build.Id(), "bad task")
	assert.Error(suite.T(), err)
	assert.Nil(suite.T(), observer)
}

func (suite *SchedulerTest) TestNewExecutorWithInvalidIdentifiers() {
	build := newBuild()
	task := addTask(build, "task")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	defer worker.Close()

	buildObserver, err := suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
	defer buildObserver.Close()

	observer, err := suite.scheduler.NewExecutor("worker.Id()", task.task.Identity)
	assert.Error(suite.T(), err)
	assert.Nil(suite.T(), observer)

	observer, err = suite.scheduler.NewExecutor(worker.Id(), "task.task.Identity")
	assert.Error(suite.T(), err)
	assert.Nil(suite.T(), observer)
}

func (suite *SchedulerTest) TestScheduleBuildWithPriority() {
	// Test that builds with different priorities are scheduled in the correct order.

	build1 := newBuild()
	build1.priority = 1
	task1 := addTask(build1, "task1")
	defer build1.Close()

	build2 := newBuild()
	build2.priority = 2
	task2 := addTask(build2, "task2")
	defer build2.Close()

	build3 := newBuild()
	build3.priority = 3
	task3 := addTask(build3, "task3")
	defer build3.Close()

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)

	buildObserver1, err := suite.scheduler.ScheduleBuild(build1)
	assert.NoError(suite.T(), err)
	defer buildObserver1.Close()

	buildObserver2, err := suite.scheduler.ScheduleBuild(build2)
	assert.NoError(suite.T(), err)
	defer buildObserver2.Close()

	buildObserver3, err := suite.scheduler.ScheduleBuild(build3)
	assert.NoError(suite.T(), err)
	defer buildObserver3.Close()

	worker.Close()

	// Schedule task from build2 first
	taskObserver1, err := suite.scheduler.ScheduleTask(build1.Id(), task1.Identity())
	assert.NoError(suite.T(), err)
	defer taskObserver1.Close()

	taskObserver2, err := suite.scheduler.ScheduleTask(build2.Id(), task2.Identity())
	assert.NoError(suite.T(), err)
	defer taskObserver2.Close()

	taskObserver3, err := suite.scheduler.ScheduleTask(build3.Id(), task3.Identity())
	assert.NoError(suite.T(), err)
	defer taskObserver3.Close()

	worker, err = suite.newWorker()
	assert.NoError(suite.T(), err)
	defer worker.Close()

	scheduledTask := <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task3, scheduledTask)
	worker.Acknowledge()

	scheduledTask = <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	worker.Acknowledge()

	scheduledTask = <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	worker.Acknowledge()
}

func (suite *SchedulerTest) TestCancelBuild() {
	build1 := newBuild()
	build1.priority = 1
	task1 := addTask(build1, "task1")
	defer build1.Close()

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	defer worker.Close()

	buildObserver1, err := suite.scheduler.ScheduleBuild(build1)
	assert.NoError(suite.T(), err)
	defer buildObserver1.Close()

	// Schedule task from build2 first
	taskObserver1, err := suite.scheduler.ScheduleTask(build1.Id(), task1.Identity())
	assert.NoError(suite.T(), err)
	defer taskObserver1.Close()

	scheduledTask := <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)
	worker.Acknowledge()

	suite.scheduler.CancelBuild(build1.Id())

	select {
	case <-worker.Tasks():
		suite.T().FailNow()
	default:
	}
}

func (suite *SchedulerTest) TestCancelBuildWithObservers() {
	build1 := newBuild()
	build1.priority = 1
	task1 := addTask(build1, "task1")
	task2 := addTask(build1, "task2")
	defer build1.Close()

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	defer worker.Close()

	buildObserver1, err := suite.scheduler.ScheduleBuild(build1)
	assert.NoError(suite.T(), err)
	defer buildObserver1.Close()

	select {
	case update := <-buildObserver1.Updates():
		assert.Equal(suite.T(), protocol.BuildStatus_BUILD_ACCEPTED, update.Status)
	case <-time.After(1 * time.Second):
		assert.FailNow(suite.T(), "Build should have been accepted")
	}

	// Schedule task
	taskObserver1, err := suite.scheduler.ScheduleTask(build1.Id(), task1.Identity())
	assert.NoError(suite.T(), err)
	defer taskObserver1.Close()

	taskObserver2, err := suite.scheduler.ScheduleTask(build1.Id(), task2.Identity())
	assert.NoError(suite.T(), err)
	defer taskObserver2.Close()

	scheduledTask := <-worker.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)

	executor, err := suite.scheduler.NewExecutor(worker.Id(), scheduledTask.Build().Id())
	assert.NoError(suite.T(), err)

	scheduledTask = <-executor.Tasks()
	assert.NotNil(suite.T(), scheduledTask)
	assert.Equal(suite.T(), task1, scheduledTask)
	scheduledTask.PostStatusUpdate(protocol.TaskStatus_TASK_PASSED)

	suite.scheduler.CancelBuild(build1.Id())

	executor.Acknowledge()
	executor.Close()

	worker.Acknowledge()

	select {
	case <-worker.Tasks():
		assert.Fail(suite.T(), "No more tasks should be scheduled to the worker")
	default:
	}

	select {
	case update := <-taskObserver1.Updates():
		assert.NotNil(suite.T(), update)
		assert.Equal(suite.T(), protocol.TaskStatus_TASK_PASSED, update.Status)
	case <-time.After(1 * time.Second):
		assert.Fail(suite.T(), "Task1 should have been completed")
	}

	select {
	case update := <-taskObserver2.Updates():
		assert.NotNil(suite.T(), update)
		assert.Equal(suite.T(), protocol.TaskStatus_TASK_CANCELLED, update.Status)
	case <-time.After(1 * time.Second):
		assert.Fail(suite.T(), "Task2 should have been cancelled")
	}
}

func TestPriorityScheduler(t *testing.T) {
	suite.Run(t, &SchedulerTest{
		createScheduler: func() Scheduler {
			return NewPriorityScheduler()
		},
	})
}
