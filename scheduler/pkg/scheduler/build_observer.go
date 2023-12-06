package scheduler

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// Manager of task update observers.
type BuildUpdateObservers interface {
	// Create a new observer.
	NewObserver() BuildUpdateObserver

	// Returns true if there are any observers.
	HasObserver() bool

	// Post an update to all observers.
	Post(*protocol.BuildUpdate)

	// Close all observers.
	Close()
}

// Observer to be notified of task updates.
type BuildUpdateObserver interface {
	// Returns a channel of build updates.
	Updates() chan *protocol.BuildUpdate

	// Close the observer.
	Close()
}

// Implementation of TaskUpdateObserver.
type buildUpdateObservers struct {
	broadcast *utils.Broadcast[*protocol.BuildUpdate]
}

// Create a new build update observer manager.
func NewBuildUpdateObservers() BuildUpdateObservers {
	return &buildUpdateObservers{
		broadcast: utils.NewBroadcast[*protocol.BuildUpdate](),
	}
}

// Create a new observer.
func (o *buildUpdateObservers) NewObserver() BuildUpdateObserver {
	return &buildUpdateObserver{
		consumer: o.broadcast.NewConsumer(),
	}
}

// Returns true if there are any observers.
func (o *buildUpdateObservers) HasObserver() bool {
	return o.broadcast.HasConsumer()
}

// Post an update to all observers.
func (o *buildUpdateObservers) Post(update *protocol.BuildUpdate) {
	o.broadcast.Send(update)
}

// Close all observers.
func (o *buildUpdateObservers) Close() {
	o.broadcast.Close()
}

// Implementation of TaskUpdateObserver.
type buildUpdateObserver struct {
	consumer *utils.BroadcastConsumer[*protocol.BuildUpdate]
}

// Close the observer.
func (o *buildUpdateObserver) Close() {
	o.consumer.Close()
}

// Returns a channel of task updates.
func (o *buildUpdateObserver) Updates() chan *protocol.BuildUpdate {
	return o.consumer.Chan
}
