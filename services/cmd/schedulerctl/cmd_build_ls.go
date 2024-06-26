package main

import (
	"fmt"
	"log"
	"sort"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/grpc"
)

var buildListCmd = &cobra.Command{
	Use:   "ls",
	Short: "List builds",
	Run: func(cmd *cobra.Command, args []string) {
		ctx, cancel := DefaultDeadlineContext()
		defer cancel()

		maxSizeOption := grpc.MaxCallRecvMsgSize(32 * 10e6)

		request := &protocol.ListBuildsRequest{
			Tasks: cmd.Flags().Changed("tasks"),
		}

		client := NewAdminClient()
		response, err := client.ListBuilds(ctx, request, maxSizeOption)
		if err != nil {
			log.Fatal(err)
		}

		sort.Slice(response.Builds, func(i, j int) bool {
			return response.Builds[i].ScheduledAt.AsTime().Before(response.Builds[j].ScheduledAt.AsTime())
		})

		buildCount := len(response.Builds)
		buildPad := fmt.Sprint(len(fmt.Sprint(buildCount)))

		for index, build := range response.Builds {
			// Print build
			fmt.Printf("%"+buildPad+"d: %s %-15s %s Rdy:%-5t O:%-5t Q:%-5t R:%-5t\n",
				index+1,
				build.Id,
				build.Status,
				build.ScheduledAt.AsTime().Local().Format("2006-01-02T15:04:05"),
				build.Ready,
				build.HasObserver,
				build.HasQueuedTask,
				build.HasRunningTask)

			// Skip tasks if not requested
			if !cmd.Flags().Changed("tasks") {
				continue
			}

			// Sort tasks by name
			sort.Slice(build.Tasks, func(i, j int) bool {
				return build.Tasks[i].Name < build.Tasks[j].Name
			})

			// Print tasks
			taskCount := len(build.Tasks)
			taskPad := fmt.Sprint(len(fmt.Sprint(taskCount)))
			for taskIndex, task := range build.Tasks {
				taskIndexStr := fmt.Sprintf("%"+buildPad+"d.%-"+taskPad+"d", index+1, taskIndex+1)
				fmt.Printf("%s %s %-14s O:%-5t %s\n", taskIndexStr, task.Id, task.Status, task.HasObserver, task.Name)
			}

			fmt.Println()
		}
	},
}

func init() {
	buildListCmd.Flags().BoolP("tasks", "t", false, "List tasks")
	buildCmd.AddCommand(buildListCmd)
}
