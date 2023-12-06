package scheduler

import (
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type executor struct {
	scheduler     Scheduler
	queueConsumer *utils.UnicastConsumer[*Task]
}

func NewExecutor(scheduler Scheduler, consumer *utils.UnicastConsumer[*Task]) Executor {
	return &executor{
		scheduler:     scheduler,
		queueConsumer: consumer,
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

func (o *executor) Tasks() chan *Task {
	return o.queueConsumer.Chan
}
