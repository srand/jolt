package main

import (
	"github.com/spf13/viper"
)

type ControlConfig struct {
	SchedulerUri   string `mapstructure:"scheduler_uri"`
	SchedulerToken string `mapstructure:"scheduler_token"`
}

func ParseConfig() (*ControlConfig, error) {
	config := &ControlConfig{}
	config.SchedulerUri = viper.GetString("scheduler_uri")
	config.SchedulerToken = viper.GetString("scheduler_token")
	return config, nil
}
