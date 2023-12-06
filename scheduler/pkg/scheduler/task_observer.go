package scheduler

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type TaskUpdateObservers interface {
	NewObserver() TaskUpdateObserver
	HasObserver() bool
	Post(*protocol.TaskUpdate)
	Close()
}

type TaskUpdateObserver interface {
	Updates() chan *protocol.TaskUpdate
	Close()
}

type taskUpdateObservers struct {
	broadcast *utils.Broadcast[*protocol.TaskUpdate]
}

func NewTaskUpdateObservers() TaskUpdateObservers {
	return &taskUpdateObservers{
		broadcast: utils.NewBroadcast[*protocol.TaskUpdate](),
	}
}

func (o *taskUpdateObservers) NewObserver() TaskUpdateObserver {
	return &taskUpdateObserver{
		consumer: o.broadcast.NewConsumer(),
	}
}

func (o *taskUpdateObservers) HasObserver() bool {
	return o.broadcast.HasConsumer()
}

func (o *taskUpdateObservers) Post(update *protocol.TaskUpdate) {
	o.broadcast.Send(update)
}

func (o *taskUpdateObservers) Close() {
	o.broadcast.Close()
}

type taskUpdateObserver struct {
	consumer *utils.BroadcastConsumer[*protocol.TaskUpdate]
}

func (o *taskUpdateObserver) Close() {
	o.consumer.Close()
}

func (o *taskUpdateObserver) Updates() chan *protocol.TaskUpdate {
	return o.consumer.Chan
}
