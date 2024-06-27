package main

import (
	"fmt"
	"net"
	"net/url"

	"github.com/srand/jolt/scheduler/pkg/cache"
	"github.com/srand/jolt/scheduler/pkg/log"
	"google.golang.org/grpc"
	_ "google.golang.org/grpc/encoding/gzip"
)

// Sets up a gRPC server on a specific listening address and starts it.
func serveGrpc(theCache cache.Cache, address string) {
	// Parse URI
	uri, err := url.Parse(address)
	if err != nil {
		log.Fatal(err)
	}

	host := uri.Host

	switch uri.Scheme {
	case "tcp", "tcp4", "tcp6":
		if uri.Port() == "" {
			// Default port is 9090
			host = fmt.Sprintf("%s:9090", uri.Host)
		}
	case "unix":
	default:
		log.Fatalf("Unsupported protocol: %s", uri.Scheme)
	}

	// Only TCP is supported for now
	socket, err := net.Listen(uri.Scheme, host)
	if err != nil {
		log.Fatal(err)
	}

	if uri.Scheme == "unix" {
		// Set permissions on unix socket
		socket.(*net.UnixListener).SetUnlinkOnClose(true)

		log.Info("Listening on", uri.Scheme, uri.Path)
	} else {
		log.Info("Listening on", uri.Scheme, socket.Addr())
	}

	// Setup gRPC server
	opts := []grpc.ServerOption{}
	server := grpc.NewServer(opts...)
	cache.RegisterCacheServiceServer(server, cache.NewCacheService(theCache))
	if err := server.Serve(socket); err != nil {
		log.Fatal(err)
	}
}
