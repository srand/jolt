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

		for index, build := range response.Builds {
			fmt.Printf("Build %d: %s %s\n", index, build.Id, build.Status)

			sort.Slice(build.Tasks, func(i, j int) bool {
				return build.Tasks[i].Name < build.Tasks[j].Name
			})

			for taskIndex, task := range build.Tasks {
				fmt.Printf("  %4d: %s %-14s %s\n", taskIndex, task.Id, task.Status, task.Name)
			}

			fmt.Println()
		}
	},
}

func init() {
	buildCmd.AddCommand(buildListCmd)
}
