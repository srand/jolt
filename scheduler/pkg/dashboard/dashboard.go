package dashboard

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/labstack/echo/v4"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
)

type taskEvent struct {
	Event      string
	Hostname   string
	RoutingKey string `json:"routing_key,omitempty"`
	Identity   string
	Instance   string
	Name       string
	Role       string
	Log        string
}

type DashboardConfig interface {
	GetDashboardUri() string
	GetLogstashUri() string
}

type dashboardHooks struct {
	client http.Client
	config DashboardConfig
	ch     chan *taskEvent
}

func NewDashboardTelemetryHook(config DashboardConfig) *dashboardHooks {
	hooks := &dashboardHooks{
		config: config,
		ch:     make(chan *taskEvent, 1000),
	}
	go hooks.run()
	return hooks
}

func (d *dashboardHooks) formatEvent(task *scheduler.Task, status protocol.TaskStatus) *taskEvent {
	event := &taskEvent{
		Identity: task.Identity(),
		Instance: task.Instance(),
		Name:     task.Name(),
		Role:     "scheduler",
		Log:      fmt.Sprintf("%s/logs/%s", d.config.GetLogstashUri(), task.Instance()),
	}

	switch status {
	case protocol.TaskStatus_TASK_CANCELLED:
		event.Log = ""
		fallthrough
	case protocol.TaskStatus_TASK_ERROR, protocol.TaskStatus_TASK_FAILED, protocol.TaskStatus_TASK_UNSTABLE:
		event.Event = "failed"
	case protocol.TaskStatus_TASK_DOWNLOADED, protocol.TaskStatus_TASK_PASSED, protocol.TaskStatus_TASK_UPLOADED, protocol.TaskStatus_TASK_SKIPPED:
		event.Event = "finished"
	case protocol.TaskStatus_TASK_QUEUED:
		event.Event = "queued"
		event.Log = ""
	case protocol.TaskStatus_TASK_RUNNING:
		event.Event = "started"
	}

	return event
}

func (d *dashboardHooks) formatUri(event *taskEvent) string {
	return fmt.Sprintf("%s/api/v1/tasks", d.config.GetDashboardUri())
}

func (d *dashboardHooks) postEvent(event *taskEvent) error {
	data, err := json.Marshal(event)
	if err != nil {
		return err
	}

	body := bytes.NewReader(data)
	response, err := d.client.Post(d.formatUri(event), echo.MIMEApplicationJSON, body)
	if err == nil {
		response.Body.Close()
	} else {
		log.Trace("failed to post telemetry:", err)
	}
	return err
}

func (d *dashboardHooks) TaskScheduled(task *scheduler.Task) {
	d.TaskStatusChanged(task, protocol.TaskStatus_TASK_QUEUED)
}

func (d *dashboardHooks) TaskStatusChanged(task *scheduler.Task, status protocol.TaskStatus) {
	event := d.formatEvent(task, status)
	select {
	case d.ch <- event:
	default:
		log.Debug("failed sending telemetry to dashboard, channel full")
	}
}

func (d *dashboardHooks) run() {
	for event := range d.ch {
		d.postEvent(event)
	}
}
