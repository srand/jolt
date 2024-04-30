package scheduler

type priorityExecutor struct {
	scheduler *priorityScheduler
	build     *priorityBuild
	executor  Executor
}

func (o *priorityExecutor) Acknowledge() {
	o.executor.Acknowledge()
}

func (o *priorityExecutor) Close() {
	o.executor.Close()

	o.scheduler.Lock()
	defer o.scheduler.Unlock()
	if o.build.HasQueuedTask() {
		o.scheduler.enqueueBuildNoLock(o.build)
	}
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
