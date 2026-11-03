package utils

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestParseHttpUrl(t *testing.T) {
	for input, want := range map[string]string{
		"tcp://cache":         "cache:8080",
		"tcp://cache:8000":    "cache:8000",
		"tcp://:8000":         ":8000",
		"tcp://127.0.0.1":     "127.0.0.1:8080",
		"tcp://[::1]:8000":    "[::1]:8000",
		"tcp://cache:8000/ab": "cache:8000",
	} {
		address, err := ParseHttpUrl(input)
		assert.NoError(t, err, input)
		assert.Equal(t, want, address, input)
	}

	for _, input := range []string{"http://cache", "tls://cache", "cache:8000", "tcp://cache:port", "://"} {
		_, err := ParseHttpUrl(input)
		assert.Error(t, err, input)
	}
}

func TestParseGrpcUrl(t *testing.T) {
	for input, want := range map[string]string{
		"tcp://scheduler":      "scheduler:9090",
		"tls://scheduler":      "scheduler:9090",
		"tcp://scheduler:9000": "scheduler:9000",
		"tls://scheduler:9000": "scheduler:9000",
		"tcp://[::1]:9000":     "[::1]:9000",
	} {
		address, err := ParseGrpcUrl(input)
		assert.NoError(t, err, input)
		assert.Equal(t, want, address, input)
	}

	for _, input := range []string{"http://scheduler", "unix:///tmp/socket", "scheduler:9000", "tcp://scheduler:port", "://"} {
		_, err := ParseGrpcUrl(input)
		assert.Error(t, err, input)
	}
}
