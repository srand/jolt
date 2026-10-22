//go:build unix

package cache

import (
	"syscall"
	"time"
)

// Returns the user and system CPU time used by the process so far.
func processCPUTime() (time.Duration, bool) {
	var usage syscall.Rusage
	if err := syscall.Getrusage(syscall.RUSAGE_SELF, &usage); err != nil {
		return 0, false
	}
	return time.Duration(usage.Utime.Nano() + usage.Stime.Nano()), true
}
