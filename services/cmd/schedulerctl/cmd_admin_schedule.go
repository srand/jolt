package main

import (
	"log"

	"github.com/spf13/cobra"
	"google.golang.org/protobuf/types/known/emptypb"
)

var scheduleCmd = &cobra.Command{
	Use:   "reschedule",
	Short: "Force scheduler to re-evaluate builds and tasks ",
	Run: func(cmd *cobra.Command, args []string) {
		ctx, cancel := DefaultDeadlineContext()
		defer cancel()

		client := NewAdminClient()
		_, err := client.Reschedule(ctx, &emptypb.Empty{})
		if err != nil {
			log.Fatal(err)
		}
	},
}

func init() {
	rootCmd.AddCommand(scheduleCmd)
}
