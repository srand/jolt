package scheduler

type priorityExecutor struct {
	scheduler *priorityScheduler
	executor  Executor
}

func (o *priorityExecutor) Acknowledge() {
	o.executor.Acknowledge()
}

func (o *priorityExecutor) Unacknowledged() *Task {
	return o.executor.Unacknowledged()
}

func (o *priorityExecutor) Close() {
	o.executor.Close()
}

func (o *priorityExecutor) Done() <-chan struct{} {
	return o.executor.Done()
}

func (o *priorityExecutor) Platform() *Platform {
	return o.executor.Platform()
}

func (o *priorityExecutor) Tasks() chan *Task {
	return o.executor.Tasks()
}
