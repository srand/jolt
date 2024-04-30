package main

import (
	"fmt"
	"log"
	"sort"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

var buildListCmd = &cobra.Command{
	Use:   "ls",
	Short: "List builds",
	Run: func(cmd *cobra.Command, args []string) {
		ctx, cancel := DefaultDeadlineContext()
		defer cancel()

		client := NewAdminClient()
		response, err := client.ListBuilds(ctx, &protocol.ListBuildsRequest{})
		if err != nil {
			log.Fatal(err)
		}

		sort.Slice(response.Builds, func(i, j int) bool {
			return response.Builds[i].ScheduledAt.AsTime().Before(response.Builds[j].ScheduledAt.AsTime())
		})

		buildCount := len(response.Builds)
		buildPad := fmt.Sprint(len(fmt.Sprint(buildCount)))

		for index, build := range response.Builds {
			fmt.Printf("%"+buildPad+"d: %s %-15s %s\n", index+1, build.Id, build.Status, build.ScheduledAt.AsTime().Local().Format("2006-01-02T15:04:05"))

			if !cmd.Flags().Changed("tasks") {
				continue
			}

			sort.Slice(build.Tasks, func(i, j int) bool {
				return build.Tasks[i].Name < build.Tasks[j].Name
			})

			taskCount := len(build.Tasks)
			taskPad := fmt.Sprint(len(fmt.Sprint(taskCount)))

			for taskIndex, task := range build.Tasks {
				taskIndexStr := fmt.Sprintf("%"+buildPad+"d.%-"+taskPad+"d", index+1, taskIndex+1)
				fmt.Printf("%s %s %-14s %s\n", taskIndexStr, task.Id, task.Status, task.Name)
			}

			fmt.Println()
		}
	},
}

func init() {
	buildListCmd.Flags().BoolP("tasks", "t", false, "List tasks")
	buildCmd.AddCommand(buildListCmd)
}
