package worker

import (
	"errors"
	"net/url"
	"runtime"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type WorkerConfig struct {
	Grpc utils.GRPCOptions `mapstructure:"grpc"`

	// Base URL to the cache service.
	CacheHttpUri string `mapstructure:"cache_http_uri"`

	// gRPC URI to the cache service.
	CacheGrpcUri string `mapstructure:"cache_grpc_uri"`

	// Directory to use for caching.
	CacheDir string `mapstructure:"cache_dir"`

	// Whether to use Nix for building.
	Nix bool `mapstructure:"nix"`

	// Host environment variables to keep when using Nix.
	NixEnvironmentToKeep []string `mapstructure:"nix_keep"`

	// Base URL to the scheduler service.
	SchedulerGrpcUri string `mapstructure:"scheduler_grpc_uri"`

	// Thread count for the worker.
	ThreadCount int `mapstructure:"threads"`
}

// Checks if the worker configuration is valid.
func (c *WorkerConfig) Validate() error {
	// Validate the cache HTTP URI.
	if c.CacheHttpUri == "" {
		return errors.New("A cache HTTP URI is required")
	}

	// Validate the cache HTTP URI is a valid URL.
	if _, err := url.Parse(c.CacheHttpUri); err != nil {
		return errors.New("The cache HTTP URI is not a valid URI")
	}

	// Validate the cache gRPC URI is a valid URL.
	if _, err := url.Parse(c.CacheGrpcUri); err != nil {
		return errors.New("The cache gRPC URI is not a valid URI")
	}

	// Validate the scheduler URI.
	if c.SchedulerGrpcUri == "" {
		return errors.New("A scheduler URI is required")
	}

	// Validate the scheduler URI is a valid URL.
	if _, err := url.Parse(c.SchedulerGrpcUri); err != nil {
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

func (c *WorkerConfig) Log() {
	log.Info("Worker configuration:")
	log.Infof("  cache_dir = %s", c.CacheDir)
	log.Infof("  cache_http_uri = %s", c.CacheHttpUri)
	log.Infof("  cache_grpc_uri = %s", c.CacheGrpcUri)
	log.Infof("  scheduler_grpc_uri = %s", c.SchedulerGrpcUri)
	log.Infof("  nix = %v", c.Nix)
	log.Infof("  nix_keep = %v", c.NixEnvironmentToKeep)
	log.Infof("  thread_count = %v", c.ThreadCount)
	c.Grpc.Log()
}
