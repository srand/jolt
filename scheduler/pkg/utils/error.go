package utils

import "fmt"

var (
	NoEligibleWorkerError = fmt.Errorf("No eligible worker available")
	NoTaskError           = fmt.Errorf("No tasks available")
	NotFoundError         = fmt.Errorf("Not found")
)

type DetailedError interface {
	error
	Details() string
}
