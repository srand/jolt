package scheduler

import (
	"testing"
	"time"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/suite"
)

func TestTask(t *testing.T) {
	suite.Run(t, &TaskTest{})
}

type TaskTest struct {
	suite.Suite
	task *Task
}

func (suite *TaskTest) SetupTest() {
	build := newBuild()
	suite.task = addTask(build, "name", "label=test")
}

func (s *TaskTest) TestIsComplete() {
	statuses := []struct {
		status   protocol.TaskStatus
		complete bool
	}{
		{protocol.TaskStatus_TASK_CANCELLED, true},
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
		build := newBuild()
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
	case update = <-o3.Updates():
		s.FailNow("Unexpected message")
	case <-time.After(0):
	}
}
