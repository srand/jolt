//go:build linux

package utils

import (
	"github.com/srand/jolt/scheduler/pkg/log"
	"golang.org/x/sys/unix"
)

func DisableTHP() {
	// Disable transparent huge pages to workaround memory leaks
	log.Info("Disabling transparent huge pages")
	if err := unix.Prctl(unix.PR_SET_THP_DISABLE, 1, 0, 0, 0); err != nil {
		log.Warn("Failed to disable transparent huge pages:", err)
	}
}
