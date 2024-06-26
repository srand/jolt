package scheduler

import (
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/suite"
)

func TestTask(t *testing.T) {
	suite.Run(t, &TaskTest{scheduler: &priorityScheduler{}})
}

type TaskTest struct {
	suite.Suite
	scheduler *priorityScheduler
	task      *Task
}

func (suite *TaskTest) newBuild() Build {
	request := protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{
			Tasks: map[string]*protocol.Task{},
		},
	}
	uid, _ := uuid.NewRandom()
	id, _ := utils.Sha1String(uid.String())
	build := suite.scheduler.NewBuild(id, &request)
	return build
}

func (suite *TaskTest) addTask(build Build, name string, properties ...string) *Task {
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
	build.(*priorityBuild).tasks[task.Identity()] = task
	return task
}

func (suite *TaskTest) SetupTest() {
	build := suite.newBuild()
	suite.task = suite.addTask(build, "name", "label=test")
}

func (s *TaskTest) TestIsComplete() {
	statuses := []struct {
		status   protocol.TaskStatus
		complete bool
	}{
		{protocol.TaskStatus_TASK_CANCELLED, true},
		{protocol.TaskStatus_TASK_CREATED, false},
		{protocol.TaskStatus_TASK_DOWNLOADED, true},
		{protocol.TaskStatus_TASK_FAILED, true},
		{protocol.TaskStatus_TASK_PASSED, true},
		{protocol.TaskStatus_TASK_QUEUED, false},
		{protocol.TaskStatus_TASK_RUNNING, false},
		{protocol.TaskStatus_TASK_SKIPPED, true},
		{protocol.TaskStatus_TASK_UNSTABLE, true},
		{protocol.TaskStatus_TASK_UPLOADED, true},
		{protocol.TaskStatus_TASK_ERROR, true},
	}

	for _, data := range statuses {
		build := s.newBuild()
		task := addTask(build, "name", "label=test")
		task.PostUpdate(&protocol.TaskUpdate{Status: data.status})
		assert.Equal(s.T(), data.complete, task.IsCompleted(), data.status)
	}
}

func (s *TaskTest) TestObserver() {
	assert.False(s.T(), s.task.HasObserver())

	o1 := s.task.NewUpdateObserver()
	assert.True(s.T(), s.task.HasObserver())

	select {
	case <-o1.Updates():
		assert.FailNow(s.T(), "Unexpected message in queue")
	case <-time.After(0):
	}

	s.task.PostUpdate(&protocol.TaskUpdate{Status: protocol.TaskStatus_TASK_RUNNING})
	update := <-o1.Updates()
	assert.Equal(s.T(), protocol.TaskStatus_TASK_RUNNING, update.Status)

	// Second observer
	o2 := s.task.NewUpdateObserver()
	s.task.PostUpdate(&protocol.TaskUpdate{Status: protocol.TaskStatus_TASK_FAILED})
	update = <-o1.Updates()
	assert.Equal(s.T(), protocol.TaskStatus_TASK_FAILED, update.Status)
	update = <-o2.Updates()
	assert.Equal(s.T(), protocol.TaskStatus_TASK_FAILED, update.Status)

	o2.Close()
	update = <-o2.Updates()
	assert.Nil(s.T(), update)

	o1.Close()
	update = <-o1.Updates()
	assert.Nil(s.T(), update)

	assert.False(s.T(), s.task.HasObserver())

	// This update is lost, because no observer exists
	s.task.PostUpdate(&protocol.TaskUpdate{Status: protocol.TaskStatus_TASK_FAILED})
	o3 := s.task.NewUpdateObserver()
	defer o3.Close()
	select {
	case <-o3.Updates():
		s.FailNow("Unexpected message")
	case <-time.After(0):
	}
}
