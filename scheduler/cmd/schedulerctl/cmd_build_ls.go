package main

import (
	"fmt"
	"log"

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
			fmt.Printf("%d: %s\n", index+1, build.Id)
		}
	},
}

func init() {
	buildCmd.AddCommand(buildListCmd)
}
