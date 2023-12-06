package protocol

// Should return true if the task is no longer in progress
func (status BuildStatus) IsCompleted() bool {
	switch status {
	case BuildStatus_BUILD_ACCEPTED:
		return false
	default:
		return true
	}
}
