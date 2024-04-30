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

		buildCount := len(response.Builds)

		for index, build := range response.Builds {
			fmt.Printf("%d: %s %s %s\n", index, build.Id, build.Status, build.ScheduledAt.AsTime().Format("2006-01-02T15:04:05"))

			if !cmd.Flags().Changed("tasks") {
				continue
			}

			sort.Slice(build.Tasks, func(i, j int) bool {
				return build.Tasks[i].Name < build.Tasks[j].Name
			})

			taskCount := len(build.Tasks)
			maxCharCount := len(fmt.Sprint(buildCount)) + len(fmt.Sprint(taskCount)) + 2

			for taskIndex, task := range build.Tasks {
				taskIndexStr := fmt.Sprintf("%d.%d:", index, taskIndex)
				taskIndexStr = fmt.Sprintf(fmt.Sprintf("%%-%ds", maxCharCount), taskIndexStr)
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
