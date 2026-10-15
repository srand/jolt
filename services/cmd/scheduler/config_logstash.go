package main

import (
	"fmt"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// Default maximum size of the stash. A stash must not be left on a zero
// budget: the LRU reads that as zero capacity rather than as unbounded, and
// discards every log as soon as its task completes. Stored in memory unless
// disk storage is configured, so this is a RAM budget by default.
const defaultMaxSize = "1GB"

type LogStashConfig struct {
	// Maximum size of the logstash.
	// When the size is exceeded, oldest entries will be removed.
	// Supported suffixes: K, M, G, T, P, E and their binary counterparts
	// Ki, Mi, Gi, Ti, Pi, Ei, each optionally followed by B.
	// Defaults to defaultMaxSize when unset.
	MaxSize_ string `mapstructure:"size"`
	// Storage type: "memory" or "disk"
	StorageType string `mapstructure:"storage"`
	// Path to store logstash files (for disk storage)
	Path string `mapstructure:"path"`
}

func (c *LogStashConfig) MaxSize() int64 {
	size, _ := utils.ParseSize(c.MaxSize_)
	return size
}

func (c *LogStashConfig) CreateFs() (utils.Fs, error) {
	switch c.StorageType {
	case "disk":
		if c.Path == "" {
			return nil, fmt.Errorf("no path configured for logstash disk storage")
		}

		os := afero.NewOsFs()
		if err := os.MkdirAll(c.Path, 0777); err != nil {
			return nil, err
		}

		fs := afero.NewBasePathFs(os, c.Path)

		log.Info("Logstash stored in", c.Path)
		return fs, nil

	case "", "memory":
		log.Info("Logstash stored in memory")
		return afero.NewMemMapFs(), nil

	default:
		return nil, fmt.Errorf("invalid logstash storage type configured: %s", c.StorageType)
	}
}

func (c *LogStashConfig) SetDefaults() {
	if c.StorageType == "" {
		c.StorageType = "memory"
	}
	if c.MaxSize_ == "" {
		c.MaxSize_ = defaultMaxSize
	}
}

func (c *LogStashConfig) LogValues() {
	log.Infof("  Logstash configuration:")
	log.Infof("    storage = %s", c.StorageType)
	log.Infof("    size = %d", c.MaxSize())
	if c.StorageType == "disk" {
		log.Infof("    path = %s", c.Path)
	}
}
