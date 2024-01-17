package main

import (
	"fmt"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type LogStashConfig struct {
	MaxSize_    string `mapstructure:"size"`
	StorageType string `mapstructure:"storage"`
	Path        string `mapstructure:"path"`
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

		fs := afero.NewBasePathFs(afero.NewOsFs(), c.Path)

		if err := fs.MkdirAll(c.Path, 0777); err != nil {
			return nil, err
		}

		log.Info("Logstash stored at", c.Path)
		return fs, nil

	case "", "memory":
		log.Info("Logstash stored in memory")
		return afero.NewMemMapFs(), nil

	default:
		return nil, fmt.Errorf("invalid logstash storage type configured: %s", c.StorageType)
	}
}

type Config struct {
	ListenGrpc []string       `mapstructure:"listen_grpc"`
	ListenHttp []string       `mapstructure:"listen_http"`
	LogStash   LogStashConfig `mapstructure:"logstash"`
}
