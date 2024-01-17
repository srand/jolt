package main

import (
	"github.com/spf13/viper"
)

type ControlConfig struct {
	SchedulerUri string `mapstructure:"scheduler_uri"`
}

func ParseConfig() (*ControlConfig, error) {
	config := &ControlConfig{}
	config.SchedulerUri = viper.GetString("scheduler_uri")
	return config, nil
}
