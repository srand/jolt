package dashboard

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

type MockDashboardConfig struct {
	mock.Mock
}

// The URI of the Dashboard web service
func (m *MockDashboardConfig) GetDashboardUri() string {
	return m.Called().String(0)
}

// The URI or the scheduler logstash web service.
func (m *MockDashboardConfig) GetLogstashUri() string {
	return m.Called().String(0)
}

func TestDashboard(t *testing.T) {
	event := map[string]string{}
	ch := make(chan bool, 1)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		decoder := json.NewDecoder(r.Body)
		err := decoder.Decode(&event)
		assert.NoError(t, err)
		ch <- true
	}))
	defer ts.Close()

	c := &MockDashboardConfig{}
	c.On("GetLogstashUri").Return("http://logstash")
	c.On("GetDashboardUri").Return(ts.URL)

	// Mock task and build request
	taskR := &protocol.Task{
		Name:     "name",
		Identity: "identity",
		Instance: "instance",
		Platform: &protocol.Platform{
			Properties: []*protocol.Property{
				{
					Key:   "label",
					Value: "routing key",
				},
			},
		},
	}
	buildR := &protocol.BuildRequest{
		Environment: &protocol.BuildEnvironment{
			Tasks: map[string]*protocol.Task{
				"": taskR,
			},
		},
	}

	build := scheduler.NewBuildFromRequest("build1", buildR)
	task := scheduler.NewTask(build, taskR)

	d := NewDashboardTelemetryHook(c)
	defer d.Close()

	d.TaskScheduled(task)
	<-ch
	assert.Equal(t, event["Name"], task.Name())
	assert.Equal(t, event["Event"], "queued")
	assert.Equal(t, event["Identity"], "identity")
	assert.Equal(t, event["Instance"], "instance")
	assert.Equal(t, event["Hostname"], "")
	assert.Equal(t, event["Log"], "")
	assert.Equal(t, event["routing_key"], "routing key")

	platform := &scheduler.Platform{}
	platform.AddProperty("worker.hostname", "hostname")

	task.SetMatchedPlatform(platform)
	task.PostStatusUpdate(protocol.TaskStatus_TASK_RUNNING)
	d.TaskStatusChanged(task, protocol.TaskStatus_TASK_RUNNING)
	<-ch
	assert.Equal(t, event["Name"], task.Name())
	assert.Equal(t, event["Event"], "started")
	assert.Equal(t, event["Hostname"], "hostname")
	assert.Equal(t, event["Log"], "http://logstash/logs/instance")

	task.PostStatusUpdate(protocol.TaskStatus_TASK_PASSED)
	d.TaskStatusChanged(task, protocol.TaskStatus_TASK_PASSED)
	<-ch
	assert.Equal(t, event["Name"], task.Name())
	assert.Equal(t, event["Event"], "finished")
}
