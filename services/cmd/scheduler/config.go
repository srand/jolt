package main

import (
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type Config struct {
	utils.GRPCOptions `mapstructure:"grpc"`

	// Addresses to listen on for gRPC.
	ListenGrpc []string `mapstructure:"listen_grpc"`
	// Addresses to listen on for HTTP.
	ListenHttp []string `mapstructure:"listen_http"`
	// Public HTTP addresses.
	PublicHttp []string `mapstructure:"public_http"`
	// LogStash configuration.
	LogStash LogStashConfig `mapstructure:"logstash"`
	// Dashboard configuration.
	Dashboard *DashboardConfig `mapstructure:"dashboard"`
}

func (c *Config) GetDashboardUri() string {
	if c.Dashboard != nil {
		return c.Dashboard.GetDashboardUri()
	}
	return ""
}

func (c *Config) GetLogstashUri() string {
	for _, publicUri := range c.PublicHttp {
		return publicUri
	}

	return ""
}

func (c *Config) Log() {
	log.Info("Scheduler configuration:")
	log.Infof("  gRPC listen addresses: %v", config.ListenGrpc)
	log.Infof("  HTTP listen addresses: %v", config.ListenHttp)
	log.Infof("  Public HTTP addresses: %v", config.PublicHttp)
	config.LogStash.LogValues()
	config.GRPCOptions.Log()
}
