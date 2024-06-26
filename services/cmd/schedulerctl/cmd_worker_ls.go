package main

import (
	"fmt"
	"log"
	"sort"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/grpc"
)

var workerListCmd = &cobra.Command{
	Use:   "ls",
	Short: "List workers",
	Run: func(cmd *cobra.Command, args []string) {
		ctx, cancel := DefaultDeadlineContext()
		defer cancel()

		maxSizeOption := grpc.MaxCallRecvMsgSize(32 * 10e6)

		request := &protocol.ListWorkersRequest{}

		client := NewAdminClient()
		response, err := client.ListWorkers(ctx, request, maxSizeOption)
		if err != nil {
			log.Fatal(err)
		}

		sort.Slice(response.Workers, func(i, j int) bool {
			return response.Workers[i].Id < response.Workers[j].Id
		})

		workerCount := len(response.Workers)
		workerPad := fmt.Sprint(len(fmt.Sprint(workerCount)))

		for index, worker := range response.Workers {
			fmt.Printf("%"+workerPad+"d: %s\n",
				index+1,
				worker.Id,
			)

			// Print platform properties
			fmt.Println("  Platform")
			for _, prop := range worker.Platform.Properties {
				fmt.Printf("    %s: %s\n", prop.Key, prop.Value)
			}
			fmt.Println()

			if len(worker.TaskPlatform.Properties) > 0 {
				fmt.Println("  Task platform")
				for _, prop := range worker.TaskPlatform.Properties {
					fmt.Printf("    %s: %s\n", prop.Key, prop.Value)
				}
				fmt.Println()
			}
			if worker.Task != nil {
				fmt.Println("  Task")
				fmt.Printf("    %s %s %s\n", worker.Task.Id, worker.Task.Status, worker.Task.Name)
				fmt.Println()
			}
		}
	},
}

func init() {
	workerCmd.AddCommand(workerListCmd)
}
