package scheduler

import "fmt"

var (
	NoEligibleWorkerError = fmt.Errorf("No eligible worker available")
	NoTaskError           = fmt.Errorf("No tasks available")
)
