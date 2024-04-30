package main

import (
	"log"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

var buildStopCmd = &cobra.Command{
	Use:   "stop [id]",
	Short: "Stop a build",
	Args:  cobra.MinimumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		ctx, cancel := DefaultDeadlineContext()
		defer cancel()

		client := NewAdminClient()

		for _, arg := range args {
			response, err := client.CancelBuild(ctx, &protocol.CancelBuildRequest{BuildId: arg})
			if err != nil {
				log.Fatal(err)
			}

			log.Println(response.Status)
		}
	},
}

func init() {
	buildCmd.AddCommand(buildStopCmd)
}
