package worker

import (
	"errors"
	"net/url"
	"runtime"
)

type WorkerConfig struct {
	// Base URL to the cache service.
	CacheUri string `mapstructure:"cache_uri"`

	CacheGrpcUri string `mapstructure:"cache_grpc_uri"`

	// Directory to use for caching.
	CacheDir string `mapstructure:"cache_dir"`

	NixEnvironmentToKeep []string `mapstructure:"nix_keep"`

	// Base URL to the scheduler service.
	SchedulerUri string `mapstructure:"scheduler_uri"`

	// Thread count for the worker.
	ThreadCount int `mapstructure:"threads"`
}

// Checks if the worker configuration is valid.
func (c *WorkerConfig) Validate() error {
	// Validate the cache URI.
	if c.CacheUri == "" {
		return errors.New("A cache URI is required")
	}

	// Validate the cache URI is a valid URL.
	if _, err := url.Parse(c.CacheUri); err != nil {
		return errors.New("The cache URI is not a valid URI")
	}

	// Validate the cache gRPC URI is a valid URL.
	if _, err := url.Parse(c.CacheGrpcUri); err != nil {
		return errors.New("The cache gRPC URI is not a valid URI")
	}

	// Validate the scheduler URI.
	if c.SchedulerUri == "" {
		return errors.New("A scheduler URI is required")
	}

	// Validate the scheduler URI is a valid URL.
	if _, err := url.Parse(c.SchedulerUri); err != nil {
		return errors.New("The scheduler URI is not a valid URI")
	}

	// Validate the thread count.
	if c.ThreadCount <= 0 {
		return errors.New("The thread count must be greater than zero")
	}
	if c.ThreadCount > runtime.NumCPU() {
		return errors.New("The thread count must be less than or equal to the number of CPUs")
	}

	return nil
}
