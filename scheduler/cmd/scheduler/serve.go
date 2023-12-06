package main

import (
	"context"
	"fmt"
	"net"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
	"google.golang.org/grpc"
)

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

	socket, err := net.Listen("tcp", fmt.Sprintf(":%d", viper.GetInt("port")))
	if err != nil {
		panic(err)
	}

	ctx := context.Background()

	sched := scheduler.NewRoundRobinScheduler()
	go sched.Run(ctx)

	opts := []grpc.ServerOption{}
	server := grpc.NewServer(opts...)
	protocol.RegisterSchedulerServer(server, scheduler.NewSchedulerService(sched))
	protocol.RegisterWorkerServer(server, scheduler.NewWorkerService(sched))
	protocol.RegisterAdministrationServer(server, scheduler.NewAdminService(sched))
	server.Serve(socket)
}
