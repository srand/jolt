package scheduler

import (
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type executor struct {
	scheduler     Scheduler
	platform      *Platform
	queueConsumer *utils.UnicastConsumer[*Task]
}

func NewExecutor(scheduler Scheduler, platform *Platform, consumer *utils.UnicastConsumer[*Task]) Executor {
	return &executor{
		platform:      platform,
		queueConsumer: consumer,
		scheduler:     scheduler,
	}
}

func (o *executor) Acknowledge() {
	o.queueConsumer.Acknowledge()
}

func (o *executor) Close() {
	o.queueConsumer.Close()
}

func (o *executor) Done() <-chan struct{} {
	return o.queueConsumer.Done()
}

func (o *executor) Platform() *Platform {
	return o.platform
}

func (o *executor) Tasks() chan *Task {
	return o.queueConsumer.Chan
}

func (o *executor) Unacknowledged() *Task {
	return o.queueConsumer.Unacknowledged()
}
