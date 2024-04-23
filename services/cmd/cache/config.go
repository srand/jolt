package main

import (
	"log"
	"time"

	"github.com/srand/jolt/scheduler/pkg/utils"
)

type Config struct {
	// Path to server certificate
	Certificate string `mapstructure:"cert"`
	// Path to service certificate private key
	PrivateKey string `mapstructure:"cert_key"`

	// Time duration from access to an artifact until the artifact
	// expires and may be evicted.
	ExpirationTime_ int64 `mapstructure:"expiration"`

	// Don't use TLS / HTTPS
	Insecure bool `mapstructure:"insecure"`

	// Addresses to listen on.
	// Ex: tcp://127.0.0.1:8080
	Listen []string `mapstructure:"listen_http"`

	// Addresses to listen on for gRPC.
	// Ex: tcp://127.0.0.1:9090
	ListenGrpc []string `mapstructure:"listen_grpc"`

	// Maximum size of cache.
	// Note that the cache may exceed this size temporarily
	// while artifacts are being uploaded and not yet have been
	// committed to the cache. It may also be exceeded if
	// there are no expired artifacts in the cache that can
	// be evicted. See ExpirationTime below.
	MaxSize_ string `mapstructure:"max_size"`

	// Filesystem path to data storage.
	// Use "memory" to store files in memory.
	Path string `mapstructure:"path"`

	// Log verbosity level: 0 = info, 1 = debug, 2 = trace
	Verbosity int `mapstructure:"verbosity"`
}

func (c *Config) MaxSize() int64 {
	size, err := utils.ParseSize(c.MaxSize_)
	if err != nil {
		log.Fatal(err)
	}
	return size
}

func (c *Config) ExpirationTime() time.Duration {
	return time.Second * time.Duration(c.ExpirationTime_)
}
