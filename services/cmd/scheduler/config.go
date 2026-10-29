package main

import (
	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type Config struct {
	utils.GRPCOptions `mapstructure:"grpc"`

	// Tokens of clients and their permissions.
	Auth auth.Config `mapstructure:"auth"`

	// Addresses to listen on for gRPC.
	ListenGrpc []string `mapstructure:"listen_grpc"`
	// Addresses to listen on for HTTP.
	ListenHttp []string `mapstructure:"listen_http"`
	// Public HTTP addresses.
	PublicHttp []string `mapstructure:"public_http"`
	// LogStash configuration.
	LogStash LogStashConfig `mapstructure:"logstash"`
}

func (c *Config) GetLogstashUri() string {
	for _, publicUri := range c.PublicHttp {
		return publicUri
	}

	return ""
}

func (c *Config) Log() {
	log.Info("Scheduler configuration:")
	log.Infof("  auth: %s", config.Auth.String())
	log.Infof("  gRPC listen addresses: %v", config.ListenGrpc)
	log.Infof("  HTTP listen addresses: %v", config.ListenHttp)
	log.Infof("  Public HTTP addresses: %v", config.PublicHttp)
	config.LogStash.LogValues()
	config.GRPCOptions.Log()
}
