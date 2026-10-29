package main

import (
	"context"
	"log"
	"time"

	"github.com/srand/jolt/scheduler/pkg/auth"
	"google.golang.org/grpc"
)

func NewSchedulerConn() *grpc.ClientConn {
	target, opts, err := auth.DialOptions(configData.SchedulerUri, auth.ClientOptions{
		CACert:             configData.CACert,
		Token:              configData.SchedulerToken,
		AllowInsecureToken: configData.AllowInsecureToken,
	})
	if err != nil {
		log.Fatal(err)
	}

	conn, err := grpc.Dial(target, opts...)
	if err != nil {
		log.Fatal(err)
	}

	return conn
}

func DefaultDeadlineContext() (context.Context, func()) {
	return context.WithDeadline(context.Background(), time.Now().Add(time.Second*30))
}
