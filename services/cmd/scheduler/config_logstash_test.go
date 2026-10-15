package main

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

// A stash without a configured size would run with a budget of zero, which the
// LRU treats as zero capacity rather than as unbounded -- every log would be
// discarded as soon as its task completed and the writer was returned to the
// cache. The default exists to keep that from being the out-of-the-box
// behaviour.
func TestSetDefaultsAppliesASizeBudget(t *testing.T) {
	config := LogStashConfig{}
	config.SetDefaults()

	assert.Greater(t, config.MaxSize(), int64(0), "an unconfigured stash must not run with a zero budget")
}

func TestSetDefaultsKeepsAConfiguredSize(t *testing.T) {
	config := LogStashConfig{MaxSize_: "10GB"}
	config.SetDefaults()

	assert.Equal(t, "10GB", config.MaxSize_)
	assert.Equal(t, int64(10*1000*1000*1000), config.MaxSize())
}

func TestSetDefaultsKeepsAConfiguredStorageType(t *testing.T) {
	config := LogStashConfig{StorageType: "disk", Path: "/tmp/logs"}
	config.SetDefaults()

	assert.Equal(t, "disk", config.StorageType)
	assert.Equal(t, "/tmp/logs", config.Path)
}

func TestSetDefaultsStoresInMemoryWhenUnconfigured(t *testing.T) {
	config := LogStashConfig{}
	config.SetDefaults()

	assert.Equal(t, "memory", config.StorageType)
}
