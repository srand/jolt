package main

import (
	"context"
	"time"

	"github.com/spf13/viper"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func NewSchedulerConn() *grpc.ClientConn {
	schedulerAddress := viper.GetString("scheduler")

	opts := grpc.WithTransportCredentials(insecure.NewCredentials())

	conn, err := grpc.Dial(schedulerAddress, opts)
	if err != nil {
		panic(err)
	}

	return conn
}

func DefaultDeadlineContext() (context.Context, func()) {
	return context.WithDeadline(context.Background(), time.Now().Add(time.Second*30))
}
