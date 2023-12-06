package main

import (
	"context"
	"fmt"
	"net"
	"net/url"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
	"google.golang.org/grpc"
)

// Sets up a gRPC server on a specific listening address and starts it.
func listenGrpc(sched scheduler.Scheduler, address string) {
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
	protocol.RegisterSchedulerServer(server, scheduler.NewSchedulerService(sched))
	protocol.RegisterWorkerServer(server, scheduler.NewWorkerService(sched))
	protocol.RegisterAdministrationServer(server, scheduler.NewAdminService(sched))
	if err := server.Serve(socket); err != nil {
		log.Fatal(err)
	}
}

// Serve starts the scheduler service.
func Serve(cmd *cobra.Command, args []string) {
	verbosity, err := cmd.Flags().GetCount("verbose")
	if err != nil {
		panic(err)
	}

	switch {
	case verbosity >= 2:
		log.SetLevel(log.TraceLevel)
	case verbosity >= 1:
		log.SetLevel(log.DebugLevel)
	}

	// Create scheduler.
	sched := scheduler.NewPriorityScheduler()

	// Start listeninig for connections on all configured addresses
	uris := viper.GetStringSlice("scheduler_listen")

	for _, uri := range uris {
		go listenGrpc(sched, uri)
	}

	// Ready to run the scheduler
	sched.Run(context.Background())
}
