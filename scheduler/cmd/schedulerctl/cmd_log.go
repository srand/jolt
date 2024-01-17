package main

import (
	"fmt"
	"io"
	"log"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/protobuf/types/known/timestamppb"
)

var logCmd = &cobra.Command{
	Use:   "log [instance-id]",
	Short: "Display task log",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		logLevel := protocol.LogLevel_STDOUT

		verbosity, _ := cmd.Flags().GetCount("verbose")
		switch verbosity {
		case 1:
			logLevel = protocol.LogLevel_VERBOSE
		case 2:
			logLevel = protocol.LogLevel_EXCEPTION
		}

		var afterTs, beforeTs *timestamppb.Timestamp

		if after, _ := cmd.Flags().GetString("after"); after != "" {
			after, err := time.Parse(time.RFC3339, after)
			if err != nil {
				log.Fatal(err)
			}
			afterTs = timestamppb.New(after)
		}

		if before, _ := cmd.Flags().GetString("before"); before != "" {
			before, err := time.Parse(time.RFC3339, before)
			if err != nil {
				log.Fatal(err)
			}

			beforeTs = timestamppb.New(before)
		}

		ctx, cancel := DefaultDeadlineContext()
		defer cancel()

		client := protocol.NewLogStashClient(NewSchedulerConn())

		request := &protocol.ReadLogRequest{
			Id:     args[0],
			After:  afterTs,
			Before: beforeTs,
		}

		response, err := client.ReadLog(ctx, request)
		if err != nil {
			log.Fatal(err)
		}

		for {
			record, err := response.Recv()
			if err == io.EOF {
				break
			}

			if err != nil {
				log.Fatal(err)
			}

			for _, line := range record.Loglines {
				if line.Level >= logLevel {
					switch line.Level {
					case protocol.LogLevel_ERROR, protocol.LogLevel_EXCEPTION, protocol.LogLevel_STDERR:
						fmt.Printf("%s \u001b[31m%7s - %s\u001b[0m\n", line.Time.AsTime().Local().Format(time.RFC3339), strings.ToLower(line.Level.String()), line.Message)
					case protocol.LogLevel_WARNING:
						fmt.Printf("%s \u001b[33m%7s - %s\u001b[0m\n", line.Time.AsTime().Local().Format(time.RFC3339), strings.ToLower(line.Level.String()), line.Message)
					default:
						fmt.Printf("%s %7s - %s\n", line.Time.AsTime().Local().Format(time.RFC3339), strings.ToLower(line.Level.String()), line.Message)
					}
				}
			}
		}
	},
}

func init() {
	logCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable: -v, -vv)")
	logCmd.Flags().StringP("after", "a", "", "Start timestamp for log lines (RCF3339 format)")
	logCmd.Flags().StringP("before", "b", "", "End timestamp for log lines (RCF3339 format)")
	rootCmd.AddCommand(logCmd)
}
