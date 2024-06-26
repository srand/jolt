package dashboard

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/labstack/echo/v4"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
)

// The event data structure expected by the Jolt Dashbord /api/v1/tasks endpoint.
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

// Configuration properties required by the dashboard telemetry hooks
type DashboardConfig interface {
	// The URI of the Dashboard web service
	GetDashboardUri() string

	// The URI or the scheduler logstash web service.
	GetLogstashUri() string
}

type dashboardHooks struct {
	client http.Client
	config DashboardConfig
	ch     chan *taskEvent
	uri    string
}

func NewDashboardTelemetryHook(config DashboardConfig) *dashboardHooks {
	hooks := &dashboardHooks{
		config: config,
		ch:     make(chan *taskEvent, 1000),
		uri:    fmt.Sprintf("%s/api/v1/tasks", config.GetDashboardUri()),
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

	// Include required labels as the routing key field
	if labels, ok := task.Platform().GetPropertiesForKey("label"); ok {
		event.RoutingKey = strings.Join(labels, ",")
	}

	// Include hostname of worker in the event
	if pfm := task.MatchedPlatform(); pfm != nil {
		if hostname := pfm.GetHostname(); hostname != "" {
			event.Hostname = hostname
		}
	}

	switch status {
	case protocol.TaskStatus_TASK_CANCELLED:
		event.Log = ""
		event.Event = "cancelled"
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

func (d *dashboardHooks) postEvent(event *taskEvent) error {
	data, err := json.Marshal(event)
	if err != nil {
		return err
	}

	body := bytes.NewReader(data)
	response, err := d.client.Post(d.uri, echo.MIMEApplicationJSON, body)
	if err == nil {
		response.Body.Close()
	} else {
		log.Trace("failed to post telemetry:", err)
	}
	return err
}

func (d *dashboardHooks) Close() {
	close(d.ch)
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
