package main

import (
	"context"
	"fmt"
	"io"
	"math/rand"
	"time"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/timestamppb"
)

var mockExecutorCmd = &cobra.Command{
	Use:   "executor",
	Short: "Mock worker executor",
	Run: func(cmd *cobra.Command, args []string) {
		buildId, err := cmd.Flags().GetString("build")
		if err != nil {
			panic(err)
		}
		schedulerAddr, err := cmd.Flags().GetString("scheduler")
		if err != nil {
			panic(err)
		}
		workerId, err := cmd.Flags().GetString("worker")
		if err != nil {
			panic(err)
		}

		opts := grpc.WithTransportCredentials(insecure.NewCredentials())
		conn, err := grpc.Dial(schedulerAddr, opts)
		if err != nil {
			panic(err)
		}
		defer conn.Close()

		client := protocol.NewWorkerClient(conn)

		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()

		stream, err := client.GetTasks(ctx)
		if err != nil {
			panic(err)
		}
		defer stream.CloseSend()

		log.Info("Enlisting executor with scheduler")
		update := &protocol.TaskUpdate{
			BuildId:  buildId,
			WorkerId: workerId,
			Status:   protocol.TaskStatus_TASK_PASSED,
		}
		err = stream.Send(update)
		if err != nil {
			panic(err)
		}

		for {
			task, err := stream.Recv()
			if err == io.EOF {
				return
			}
			if err != nil {
				panic(err)
			}
			log.Info("Got task execution request:", task.TaskId)

			for i := 0; i < rand.Intn(100); i++ {
				time.Sleep(time.Millisecond * 100)

				log.Info("Sending update:", i)

				err = stream.Send(&protocol.TaskUpdate{
					WorkerId: workerId,
					BuildId:  buildId,
					Request:  task,
					Status:   protocol.TaskStatus_TASK_RUNNING,
					Loglines: []*protocol.LogLine{
						&protocol.LogLine{Level: protocol.LogLevel_INFO, Time: timestamppb.Now(), Message: fmt.Sprint(i)},
					},
				})
				if err != nil {
					panic(err)
				}
			}

			err = stream.Send(&protocol.TaskUpdate{
				WorkerId: workerId,
				BuildId:  buildId,
				Request:  task,
				Status:   protocol.TaskStatus_TASK_PASSED,
			})
			if err != nil {
				panic(err)
			}
			log.Info("Sent task execution response:", task.TaskId)
		}
	},
}

func init() {
	mockExecutorCmd.Flags().StringP("build", "b", "", "Build identifier")
	mockExecutorCmd.Flags().StringP("worker", "w", "", "Worker identifier")
	mockExecutorCmd.Flags().StringP("scheduler", "s", "localhost:9090", "Address of scheduler service")
	mockCmd.AddCommand(mockExecutorCmd)
}
