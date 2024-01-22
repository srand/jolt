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
		{"123K", 123 * 1024},
		{"123KB", 123 * 1024},
		{"123M", 123 * 1024 * 1024},
		{"123MB", 123 * 1024 * 1024},
		{"123G", 123 * 1024 * 1024 * 1024},
		{"123GB", 123 * 1024 * 1024 * 1024},
		{"123T", 123 * 1024 * 1024 * 1024 * 1024},
		{"123TB", 123 * 1024 * 1024 * 1024 * 1024},
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
		{"123KB", 123 * 1024},
		{"123.0MB", 123 * 1024 * 1024},
		{"123.5MB", 123*1024*1024 + 511*1024},
		{"123.00GB", 123 * 1024 * 1024 * 1024},
		{"123.00TB", 123 * 1024 * 1024 * 1024 * 1024},
	}

	for _, data := range testData {
		size := HumanByteSize(data.input)
		assert.Equal(t, data.value, size)
	}
}
