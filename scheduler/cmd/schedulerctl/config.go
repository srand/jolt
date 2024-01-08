package main

import (
	"github.com/spf13/viper"
)

type ControlConfig struct {
	SchedulerUri string `mapstructure:"scheduler_uri"`
}

func LoadConfig() (*ControlConfig, error) {
	config := &ControlConfig{}
	err := viper.Unmarshal(config)
	if err != nil {
		return nil, err
	}

	return config, nil
}
