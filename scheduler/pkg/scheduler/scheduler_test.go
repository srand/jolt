package scheduler

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/suite"
)

type SchedulerTest struct {
	suite.Suite
	scheduler Scheduler
	build     Build
	worker    Worker
	ctx       context.Context
	cancel    func()
}

func (suite *SchedulerTest) SetupTest() {
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
	id, _ := utils.Sha1String(request.String())
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

	err = suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)

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

	err := suite.scheduler.ScheduleBuild(build)
	assert.Error(suite.T(), err)
}

func (suite *SchedulerTest) TestScheduleBuildWithNoEligibleWorker() {
	build := newBuild()
	addTask(build, "task", "label=label")

	worker, err := suite.newWorker()
	defer worker.Close()

	err = suite.scheduler.ScheduleBuild(build)
	assert.Error(suite.T(), err)
}

func (suite *SchedulerTest) TestScheduleBuildWithOneWorker() {
	build := newBuild()
	addTask(build, "task")

	worker, err := suite.newWorker()
	defer worker.Close()

	err = suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
}

func (suite *SchedulerTest) TestScheduleBuildWithEligibleWorker() {
	build := newBuild()
	addTask(build, "task", "label=one")

	worker, err := suite.newWorker("label=one")
	defer worker.Close()

	err = suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)
}

func (suite *SchedulerTest) TestScheduleTask() {
	build := newBuild()
	task1 := addTask(build, "task1")
	task2 := addTask(build, "task2")

	worker, err := suite.newWorker()

	err = suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)

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
	task1 := addTask(build, "task1")
	addTask(build, "task2")

	worker, err := suite.newWorker()
	assert.NoError(suite.T(), err)
	assert.NotNil(suite.T(), worker)

	err = suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)

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
	defer worker.Close()

	err = suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)

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
	defer worker.Close()

	err = suite.scheduler.ScheduleBuild(build)
	assert.NoError(suite.T(), err)

	observer, err := suite.scheduler.NewExecutor("worker.Id()", task.task.Identity)
	assert.Error(suite.T(), err)
	assert.Nil(suite.T(), observer)

	observer, err = suite.scheduler.NewExecutor(worker.Id(), "task.task.Identity")
	assert.Error(suite.T(), err)
	assert.Nil(suite.T(), observer)
}

func TestRoundRobinScheduler(t *testing.T) {
	suite.Run(t, &SchedulerTest{
		scheduler: NewRoundRobinScheduler(),
	})
}
