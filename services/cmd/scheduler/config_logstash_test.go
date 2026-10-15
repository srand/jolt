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

func TestValidateRejectsAnUnparseableSize(t *testing.T) {
	config := LogStashConfig{MaxSize_: "abc"}

	err := config.Validate()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "abc", "the error should name the offending value")
}

// ParseSize's pattern is unanchored, so this yields a single byte rather than
// an error -- a stash that size discards every log as soon as its task
// completes, which is the failure the size budget exists to prevent. A typo
// must not be able to reinstate it quietly.
func TestValidateRejectsASizeThatParsesToNearlyNothing(t *testing.T) {
	for _, size := range []string{"1.5GB", "1 potato"} {
		config := LogStashConfig{MaxSize_: size}

		err := config.Validate()
		assert.Error(t, err, "size %q parses to one byte and must not be accepted", size)
	}
}

func TestValidateRejectsAnExplicitZeroSize(t *testing.T) {
	config := LogStashConfig{MaxSize_: "0"}

	assert.Error(t, config.Validate(), "a zero budget keeps nothing and must fail loudly")
}

func TestValidateAcceptsAConfiguredSize(t *testing.T) {
	for _, size := range []string{"10GB", "1GB", "512MiB"} {
		config := LogStashConfig{MaxSize_: size}

		assert.NoError(t, config.Validate(), "size %q should be accepted", size)
	}
}

func TestValidateAcceptsTheDefault(t *testing.T) {
	config := LogStashConfig{}
	config.SetDefaults()

	assert.NoError(t, config.Validate(), "the default must pass its own validation")
}
