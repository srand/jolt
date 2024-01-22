package main

import (
	"context"
	"log"
	"time"

	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func NewSchedulerConn() *grpc.ClientConn {
	opts := grpc.WithTransportCredentials(insecure.NewCredentials())

	grpcHost, err := utils.ParseGrpcUrl(configData.SchedulerUri)
	if err != nil {
		log.Fatal(err)
	}

	conn, err := grpc.Dial(grpcHost, opts)
	if err != nil {
		log.Fatal(err)
	}

	return conn
}

func DefaultDeadlineContext() (context.Context, func()) {
	return context.WithDeadline(context.Background(), time.Now().Add(time.Second*30))
}
