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
