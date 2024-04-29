package protocol

// Should return true if the task is no longer in progress
func (status TaskStatus) IsCompleted() bool {
	switch status {
	case TaskStatus_TASK_CREATED, TaskStatus_TASK_QUEUED, TaskStatus_TASK_RUNNING:
		return false
	default:
		return true
	}
}

// Should return true if the task is no longer in progress
func (status TaskStatus) IsCancellable() bool {
	switch status {
	case TaskStatus_TASK_QUEUED:
		return true
	default:
		return false
	}
}
