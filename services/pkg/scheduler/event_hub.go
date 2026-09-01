package scheduler

import (
	"context"
	"fmt"
	"time"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

const (
	// Interval between keepalives sent on otherwise idle event streams.
	eventHeartbeatInterval = 30 * time.Second

	// Depth of the hub's input queue. Producers block when it is full,
	// which throttles the scheduler rather than corrupting the mirror.
	eventQueueDepth = 1024
)

// EventHub mirrors the observable state of the scheduler and serves it to
// subscribers as a snapshot followed by a stream of incremental updates.
//
// The mirror is maintained by a single goroutine which also performs the
// fan-out, so a subscriber can never miss or duplicate an update that
// straddles its snapshot. Deriving the snapshot from the scheduler itself
// would require taking the scheduler lock from within an observer callback
// that already holds a task lock, which risks lock inversion.
type EventHub struct {
	// Base URI from which task logs can be downloaded.
	logstashUri string

	broadcast *utils.Broadcast[*protocol.SchedulerEvent]
	incoming  chan *eventUpdate
	done      chan struct{}

	// Tasks that have not reached a terminal status, by instance.
	tasks map[string]*protocol.TaskInfo

	// Connected workers, by worker id.
	workers map[string]*protocol.WorkerInfo
}

// An update to apply to the mirror. Exactly one field is set.
// Subscriptions travel the same queue as state updates so that a snapshot can
// never overtake an update that was posted before it.
type eventUpdate struct {
	task          *protocol.TaskInfo
	worker        *protocol.WorkerInfo
	workerRemoved string
	subscribe     *subscribeRequest
}

type subscribeRequest struct {
	filter *EventFilter
	result chan *utils.BroadcastConsumer[*protocol.SchedulerEvent]
}

func NewEventHub(logstashUri string) *EventHub {
	return &EventHub{
		logstashUri: logstashUri,
		broadcast:   utils.NewBroadcast[*protocol.SchedulerEvent](),
		incoming:    make(chan *eventUpdate, eventQueueDepth),
		done:        make(chan struct{}),
		tasks:       map[string]*protocol.TaskInfo{},
		workers:     map[string]*protocol.WorkerInfo{},
	}
}

// Run processes state updates and subscriptions until the context is cancelled.
func (h *EventHub) Run(ctx context.Context) {
	ticker := time.NewTicker(eventHeartbeatInterval)
	defer ticker.Stop()
	defer close(h.done)
	defer h.broadcast.Close()

	for {
		select {
		case <-ctx.Done():
			return

		case update := <-h.incoming:
			h.apply(update, time.Now())

		case now := <-ticker.C:
			h.broadcast.Send(&protocol.SchedulerEvent{
				Event: &protocol.SchedulerEvent_Heartbeat{
					Heartbeat: timestamppb.New(now),
				},
			})
		}
	}
}

// Subscribe registers a new event consumer. Unless suppressed by the filter,
// the first message on the returned channel is a snapshot of the current state.
func (h *EventHub) Subscribe(ctx context.Context, filter *EventFilter) (*utils.BroadcastConsumer[*protocol.SchedulerEvent], error) {
	request := &subscribeRequest{
		filter: filter,
		result: make(chan *utils.BroadcastConsumer[*protocol.SchedulerEvent], 1),
	}

	select {
	case h.incoming <- &eventUpdate{subscribe: request}:
	case <-h.done:
		return nil, utils.ErrTerminated
	case <-ctx.Done():
		return nil, ctx.Err()
	}

	select {
	case consumer := <-request.result:
		return consumer, nil
	case <-h.done:
		return nil, utils.ErrTerminated
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// Must only be called from the hub goroutine.
func (h *EventHub) subscribe(filter *EventFilter) *utils.BroadcastConsumer[*protocol.SchedulerEvent] {
	consumer := h.broadcast.NewConsumer()

	if filter == nil || !filter.NoSnapshot {
		snapshot := &protocol.Snapshot{Timestamp: timestamppb.Now()}

		for _, task := range h.tasks {
			if filter.MatchTask(task) {
				snapshot.Tasks = append(snapshot.Tasks, task)
			}
		}
		for _, worker := range h.workers {
			if filter.MatchWorker(worker) {
				snapshot.Workers = append(snapshot.Workers, worker)
			}
		}

		consumer.Chan <- &protocol.SchedulerEvent{
			Event: &protocol.SchedulerEvent_Snapshot{Snapshot: snapshot},
		}
	}

	return consumer
}

// Must only be called from the hub goroutine.
func (h *EventHub) apply(update *eventUpdate, now time.Time) {
	switch {
	case update.task != nil:
		h.applyTask(update.task, now)
	case update.worker != nil:
		h.applyWorker(update.worker)
	case update.workerRemoved != "":
		h.removeWorker(update.workerRemoved)
	case update.subscribe != nil:
		update.subscribe.result <- h.subscribe(update.subscribe.filter)
	}
}

func (h *EventHub) applyTask(info *protocol.TaskInfo, now time.Time) {
	timestamp := timestamppb.New(now)
	previousWorkerId := ""

	if previous, ok := h.tasks[info.Instance]; ok {
		previousWorkerId = previous.WorkerId
		info.QueuedAt = previous.QueuedAt
		info.StartedAt = previous.StartedAt

		// Status updates posted by the worker carry no assignment.
		if info.WorkerId == "" {
			info.WorkerId = previous.WorkerId
		}
		if info.WorkerHostname == "" {
			info.WorkerHostname = previous.WorkerHostname
		}
	}

	switch {
	case info.Status == protocol.TaskStatus_TASK_QUEUED:
		// The task may have been returned to the queue after being assigned.
		info.StartedAt = nil
		info.EndedAt = nil
		info.WorkerId = ""
		info.WorkerHostname = ""
	case info.Status == protocol.TaskStatus_TASK_RUNNING && info.StartedAt == nil:
		info.StartedAt = timestamp
	case info.Status.IsCompleted():
		info.EndedAt = timestamp
	}

	if info.QueuedAt == nil {
		info.QueuedAt = timestamp
	}

	if info.Status.IsCompleted() {
		delete(h.tasks, info.Instance)
	} else {
		h.tasks[info.Instance] = info
	}

	h.broadcast.Send(&protocol.SchedulerEvent{
		Event: &protocol.SchedulerEvent_Task{Task: info},
	})

	if previousWorkerId != "" && previousWorkerId != info.WorkerId {
		h.assignTask(previousWorkerId, info.Instance, nil)
	}
	if info.WorkerId != "" {
		if info.Status.IsCompleted() {
			h.assignTask(info.WorkerId, info.Instance, nil)
		} else {
			h.assignTask(info.WorkerId, info.Instance, info)
		}
	}
}

// Keeps the task assignment of a mirrored worker in sync with the task.
// Assignments are only cleared for the task that currently holds the worker.
func (h *EventHub) assignTask(workerId, instance string, assigned *protocol.TaskInfo) {
	worker, ok := h.workers[workerId]
	if !ok {
		return
	}

	current := worker.Task.GetInstance()

	if assigned == nil {
		if current != instance {
			return
		}
	} else if current == instance && worker.Task.GetStatus() == assigned.Status {
		return
	}

	// Published messages must stay immutable, so replace rather than mutate.
	updated := proto.Clone(worker).(*protocol.WorkerInfo)
	updated.Task = assigned
	h.workers[worker.Id] = updated

	h.broadcast.Send(&protocol.SchedulerEvent{
		Event: &protocol.SchedulerEvent_Worker{Worker: updated},
	})
}

func (h *EventHub) applyWorker(info *protocol.WorkerInfo) {
	h.workers[info.Id] = info
	h.broadcast.Send(&protocol.SchedulerEvent{
		Event: &protocol.SchedulerEvent_Worker{Worker: info},
	})
}

func (h *EventHub) removeWorker(id string) {
	if _, ok := h.workers[id]; !ok {
		return
	}

	delete(h.workers, id)
	h.broadcast.Send(&protocol.SchedulerEvent{
		Event: &protocol.SchedulerEvent_WorkerRemoved{
			WorkerRemoved: &protocol.WorkerRemoved{Id: id},
		},
	})
}

// Blocks if the hub is congested. The hub goroutine never blocks on a
// subscriber, so this only throttles the scheduler while the mirror catches up.
func (h *EventHub) post(update *eventUpdate) {
	select {
	case h.incoming <- update:
	case <-h.done:
		log.Trace("event hub is closed, discarding update")
	}
}

func (h *EventHub) newTaskInfo(task *Task, status protocol.TaskStatus, worker Worker) *protocol.TaskInfo {
	info := &protocol.TaskInfo{
		BuildId:  task.Build().Id(),
		Identity: task.Identity(),
		Instance: task.Instance(),
		Name:     task.Name(),
		Status:   status,
		Log:      fmt.Sprintf("%s/logs/%s", h.logstashUri, task.Instance()),
	}

	if labels, ok := task.Platform().GetPropertiesForKey("label"); ok {
		info.Labels = labels
	}

	if platform := task.MatchedPlatform(); platform != nil {
		info.WorkerHostname = platform.GetHostname()
	}

	if worker != nil {
		info.WorkerId = worker.Id()
	}

	switch status {
	case protocol.TaskStatus_TASK_QUEUED, protocol.TaskStatus_TASK_CANCELLED:
		info.Log = ""
	}

	return info
}

// Implementation of SchedulerObserver interface.
func (h *EventHub) TaskScheduled(task *Task) {
	h.post(&eventUpdate{
		task: h.newTaskInfo(task, protocol.TaskStatus_TASK_QUEUED, task.Worker()),
	})
}

// Implementation of SchedulerObserver interface.
func (h *EventHub) TaskStatusChanged(task *Task, status protocol.TaskStatus) {
	// Called with the task's write lock held, so the assignment cannot change
	// underneath us and must be read without locking again.
	h.post(&eventUpdate{task: h.newTaskInfo(task, status, task.worker)})
}

// Implementation of SchedulerObserver interface.
func (h *EventHub) WorkerEnlisted(worker Worker) {
	h.post(&eventUpdate{
		worker: &protocol.WorkerInfo{
			Id:           worker.Id(),
			Hostname:     worker.Platform().GetHostname(),
			Platform:     worker.Platform().Protobuf(),
			TaskPlatform: worker.TaskPlatform().Protobuf(),
			EnlistedAt:   timestamppb.Now(),
		},
	})
}

// Implementation of SchedulerObserver interface.
func (h *EventHub) WorkerDelisted(worker Worker) {
	h.post(&eventUpdate{workerRemoved: worker.Id()})
}
