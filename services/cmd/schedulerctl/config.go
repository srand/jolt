package main

import (
	"github.com/spf13/viper"
)

type ControlConfig struct {
	AllowInsecureToken bool   `mapstructure:"allow_insecure_token"`
	CACert             string `mapstructure:"ca_cert"`
	SchedulerUri       string `mapstructure:"scheduler_uri"`
	SchedulerToken     string `mapstructure:"scheduler_token"`
}

func ParseConfig() (*ControlConfig, error) {
	config := &ControlConfig{}
	config.SchedulerUri = viper.GetString("scheduler_uri")
	config.SchedulerToken = viper.GetString("scheduler_token")
	config.CACert = viper.GetString("ca_cert")
	config.AllowInsecureToken = viper.GetBool("allow_insecure_token")
	return config, nil
}
