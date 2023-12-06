package scheduler

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// Manager of task update observers.
type TaskUpdateObservers interface {
	// Create a new observer.
	NewObserver() TaskUpdateObserver

	// Returns true if there are any observers.
	HasObserver() bool

	// Post an update to all observers.
	Post(*protocol.TaskUpdate)

	// Close all observers.
	Close()
}

// Observer to be notified of task updates.
type TaskUpdateObserver interface {
	// Returns a channel of task updates.
	Updates() chan *protocol.TaskUpdate

	// Close the observer.
	Close()
}

// Implementation of TaskUpdateObserver.
type taskUpdateObservers struct {
	broadcast *utils.Broadcast[*protocol.TaskUpdate]
}

// Create a new task update observer manager.
func NewTaskUpdateObservers() TaskUpdateObservers {
	return &taskUpdateObservers{
		broadcast: utils.NewBroadcast[*protocol.TaskUpdate](),
	}
}

// Create a new observer.
func (o *taskUpdateObservers) NewObserver() TaskUpdateObserver {
	return &taskUpdateObserver{
		consumer: o.broadcast.NewConsumer(),
	}
}

// Returns true if there are any observers.
func (o *taskUpdateObservers) HasObserver() bool {
	return o.broadcast.HasConsumer()
}

// Post an update to all observers.
func (o *taskUpdateObservers) Post(update *protocol.TaskUpdate) {
	o.broadcast.Send(update)
}

// Close all observers.
func (o *taskUpdateObservers) Close() {
	o.broadcast.Close()
}

// Implementation of TaskUpdateObserver.
type taskUpdateObserver struct {
	consumer *utils.BroadcastConsumer[*protocol.TaskUpdate]
}

// Close the observer.
func (o *taskUpdateObserver) Close() {
	o.consumer.Close()
}

// Returns a channel of task updates.
func (o *taskUpdateObserver) Updates() chan *protocol.TaskUpdate {
	return o.consumer.Chan
}
