package utils

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestParseSize(t *testing.T) {
	testData := []struct {
		input string
		value int64
	}{
		{"0", 0},
		{"0K", 0},
		{"0KB", 0},
		{"0 ", 0},
		{"0 K", 0},
		{"0 KB", 0},

		{"123KiB", 123 * 1024},
		{"123MiB", 123 * 1024 * 1024},
		{"123GiB", 123 * 1024 * 1024 * 1024},
		{"123TiB", 123 * 1024 * 1024 * 1024 * 1024},

		{"123K", 123 * 1000},
		{"123KB", 123 * 1000},
		{"123M", 123 * 1000 * 1000},
		{"123MB", 123 * 1000 * 1000},
		{"123G", 123 * 1000 * 1000 * 1000},
		{"123GB", 123 * 1000 * 1000 * 1000},
		{"123T", 123 * 1000 * 1000 * 1000 * 1000},
		{"123TB", 123 * 1000 * 1000 * 1000 * 1000},
	}

	for _, data := range testData {
		size, err := ParseSize(data.input)
		assert.NoError(t, err)
		assert.Equal(t, data.value, size)
	}
}

func TestHumanByteSize(t *testing.T) {
	testData := []struct {
		value string
		input int64
	}{
		{"0B", 0},
		{"123KiB", 123 * 1024},
		{"123.0MiB", 123 * 1024 * 1024},
		{"123.5MiB", 123*1024*1024 + 511*1024},
		{"123.00GiB", 123 * 1024 * 1024 * 1024},
		{"123.00TiB", 123 * 1024 * 1024 * 1024 * 1024},
	}

	for _, data := range testData {
		size := HumanByteSize(data.input)
		assert.Equal(t, data.value, size)
	}
}

// The pattern must match the whole string. Unanchored, it matched a leading
// prefix and ignored the rest, so malformed input parsed successfully into a
// value nobody asked for: "1.5GB" became a single byte and "1 potato" became
// one too, while "-5GB" became five gigabytes.
func TestParseSizeRejectsMalformedInput(t *testing.T) {
	for _, input := range []string{
		"",
		"abc",
		"GB",
		"GB1",
		"1GG",
		"1GBB",
		"-5GB",
		"1.5GB",
		"1,5GB",
		"1 2GB",
		"1 potato",
	} {
		size, err := ParseSize(input)
		assert.Error(t, err, "input %q must be rejected", input)
		assert.Equal(t, int64(0), size, "a rejected input must not yield a size")
	}
}

func TestParseSizeAcceptsAByteCountWithoutASuffix(t *testing.T) {
	for _, input := range []string{"123", "123B"} {
		size, err := ParseSize(input)
		assert.NoError(t, err)
		assert.Equal(t, int64(123), size)
	}
}

func TestParseSizeIgnoresSurroundingWhitespace(t *testing.T) {
	size, err := ParseSize("  123 KiB  ")
	assert.NoError(t, err)
	assert.Equal(t, int64(123*1024), size)
}
