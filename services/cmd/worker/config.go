package main

import (
	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/srand/jolt/scheduler/pkg/worker"
)

func LoadConfig() (*worker.WorkerConfig, error) {
	config := &worker.WorkerConfig{}

	err := utils.UnmarshalConfig(*viper.GetViper(), config)
	if err != nil {
		return nil, err
	}

	return config, nil
}
