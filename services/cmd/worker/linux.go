//go:build linux

package main

import (
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

func init() {
	log.Info("Detected Linux")

	// Disable transparent huge pages to workaround memory leaks
	utils.DisableTHP()
}
