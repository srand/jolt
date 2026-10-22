//go:build !unix

package cache

import "time"

// Process CPU time is not measured on this platform.
func processCPUTime() (time.Duration, bool) {
	return 0, false
}
