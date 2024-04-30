package main

import (
	"context"
	"io"
	"log"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

var mockTaskCmd = &cobra.Command{
	Use:   "task [task]",
	Short: "Schedule task with scheduler service and then cancel it",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		buildId, err := cmd.Flags().GetString("build")
		if err != nil {
			panic(err)
		}

		conn := NewSchedulerConn()
		client := protocol.NewSchedulerClient(conn)

		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()

		identity, _ := utils.Sha1String(args[0])
		request := &protocol.TaskRequest{
			BuildId: buildId,
			TaskId:  identity,
		}

		stream, err := client.ScheduleTask(ctx, request)
		if err != nil {
			panic(err)
		}

		for {
			response, err := stream.Recv()
			if err == io.EOF {
				break
			}
			if err != nil {
				log.Fatal(err)
			}

			log.Println(response)
		}

		cancel()
	},
}

func init() {
	mockTaskCmd.Flags().StringP("build", "b", "", "Build identifier")
	mockCmd.AddCommand(mockTaskCmd)
}
