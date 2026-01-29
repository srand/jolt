package utils

import (
	"time"

	"github.com/srand/jolt/scheduler/pkg/log"
	"google.golang.org/grpc"
	"google.golang.org/grpc/keepalive"
)

type GRPCOptions struct {
	// The interval in milliseconds between PING frames.
	KeepAliveTime *time.Duration `mapstructure:"keep_alive_time"`
	// The timeout in milliseconds for a PING frame to be acknowledged.
	KeepAliveTimeout *time.Duration `mapstructure:"keep_alive_timeout"`
	// Send keepalive pings even if there are no active streams (client).
	KeepAliveWithoutCalls *bool `mapstructure:"keep_alive_without_calls"`
	// Are clients allowed to send keepalive pings without active streams (server).
	PermitKeepAliveWithoutCalls *bool `mapstructure:"permit_keep_alive_without_calls"`
	// Minimum allowed time between a server receiving successive ping frames without sending any data/header frame.
	PermitKeepAliveTime *time.Duration `mapstructure:"permit_keep_alive_time"`
}

func (o *GRPCOptions) ToServerOptions() []grpc.ServerOption {
	opts := []grpc.ServerOption{}

	serverParameters := keepalive.ServerParameters{}
	enforcePolicy := keepalive.EnforcementPolicy{}

	// Check server parameters
	if o.KeepAliveTime != nil {
		serverParameters.Time = *o.KeepAliveTime
	}

	if o.KeepAliveTimeout != nil {
		serverParameters.Timeout = *o.KeepAliveTimeout
	}

	if o.KeepAliveTime != nil || o.KeepAliveTimeout != nil {
		opts = append(opts, grpc.KeepaliveParams(serverParameters))
	}

	// Check enforcement policy
	if o.PermitKeepAliveWithoutCalls != nil {
		enforcePolicy.PermitWithoutStream = *o.PermitKeepAliveWithoutCalls
	}

	if o.PermitKeepAliveTime != nil {
		enforcePolicy.MinTime = *o.PermitKeepAliveTime
	}

	if o.PermitKeepAliveWithoutCalls != nil || o.PermitKeepAliveTime != nil {
		opts = append(opts, grpc.KeepaliveEnforcementPolicy(enforcePolicy))
	}

	return opts
}

func (o *GRPCOptions) ToDialOptions() []grpc.DialOption {
	opts := []grpc.DialOption{}

	kaParams := keepalive.ClientParameters{}

	if o.KeepAliveTime != nil {
		kaParams.Time = *o.KeepAliveTime
	}

	if o.KeepAliveTimeout != nil {
		kaParams.Timeout = *o.KeepAliveTimeout
	}

	if o.KeepAliveWithoutCalls != nil {
		kaParams.PermitWithoutStream = *o.KeepAliveWithoutCalls
	}

	if o.KeepAliveTime != nil || o.KeepAliveTimeout != nil || o.KeepAliveWithoutCalls != nil {
		opts = append(opts, grpc.WithKeepaliveParams(kaParams))
	}

	return opts
}

func (o *GRPCOptions) Log() {
	if o.KeepAliveTime != nil || o.KeepAliveTimeout != nil ||
		o.KeepAliveWithoutCalls != nil ||
		o.PermitKeepAliveWithoutCalls != nil ||
		o.PermitKeepAliveTime != nil {
		log.Info("  gRPC options:")
	}

	if o.KeepAliveTime != nil {
		log.Info("    keep_alive_time =", *o.KeepAliveTime)
	}

	if o.KeepAliveTimeout != nil {
		log.Info("    keep_alive_timeout =", *o.KeepAliveTimeout)
	}

	if o.KeepAliveWithoutCalls != nil {
		log.Info("    keep_alive_without_calls =", *o.KeepAliveWithoutCalls)
	}

	if o.PermitKeepAliveWithoutCalls != nil {
		log.Info("    permit_keep_alive_without_calls =", *o.PermitKeepAliveWithoutCalls)
	}

	if o.PermitKeepAliveTime != nil {
		log.Info("    permit_keep_alive_time =", *o.PermitKeepAliveTime)
	}
}
