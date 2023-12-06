package main

import (
	"context"
	"fmt"
	"io"
	"strings"

	"github.com/google/uuid"
	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

var mockBuildCmd = &cobra.Command{
	Use:   "build",
	Short: "Schedule build with scheduler service and then cancel it",
	Run: func(cmd *cobra.Command, args []string) {
		schedulerAddr, err := cmd.Flags().GetString("scheduler")
		if err != nil {
			panic(err)
		}

		platform := &protocol.Platform{
			Properties: []*protocol.Property{},
		}

		platformProps, err := cmd.Flags().GetStringSlice("platform")
		for _, prop := range platformProps {
			key, value, found := strings.Cut(prop, "=")
			if !found {
				panic("Invalid platform property: " + prop)
			}
			property := &protocol.Property{Key: key, Value: value}
			platform.Properties = append(platform.Properties, property)
		}

		tasks := map[string]*protocol.Task{}
		tasksNames, err := cmd.Flags().GetStringSlice("task")
		if err != nil {
			panic(err)
		}
		for _, taskName := range tasksNames {
			instance, _ := uuid.NewRandom()
			identity, _ := utils.Sha1String(taskName)
			tasks[taskName] = &protocol.Task{
				Name:     taskName,
				Identity: identity,
				Instance: instance.String(),
				Platform: platform,
			}
		}

		opts := grpc.WithTransportCredentials(insecure.NewCredentials())
		conn, err := grpc.Dial(schedulerAddr, opts)
		if err != nil {
			panic(err)
		}
		defer conn.Close()

		client := protocol.NewSchedulerClient(conn)

		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()

		request := &protocol.BuildRequest{
			Environment: &protocol.BuildEnvironment{
				Workspace: &protocol.Workspace{},
				Tasks:     tasks,
			},
		}

		response, err := client.ScheduleBuild(ctx, request)
		if err != nil {
			panic(err)
		}

		fmt.Println(response.BuildId, response.Status)

		chans := []chan bool{}

		for _, taskName := range tasksNames {
			done := make(chan bool)
			chans = append(chans, done)

			go func(taskName string, done chan bool) {
				defer close(done)

				identity, _ := utils.Sha1String(taskName)
				taskRequest := &protocol.TaskRequest{
					BuildId: response.BuildId,
					TaskId:  identity,
				}

				stream, err := client.ScheduleTask(ctx, taskRequest)
				if err != nil {
					panic(err)
				}

				for {
					response, err := stream.Recv()
					if err == io.EOF {
						log.Debug(err)
						break
					}
					if err != nil {
						log.Fatal(err)
					}

					log.Info(response)
				}

			}(taskName, done)
		}

		for _, ch := range chans {
			<-ch
		}

		cancel()
	},
}

func init() {
	mockBuildCmd.Flags().StringP("scheduler", "s", "localhost:9090", "Address of scheduler service")
	mockBuildCmd.Flags().StringSliceP("platform", "p", []string{}, "Platform key/value descriptor")
	mockBuildCmd.Flags().StringSliceP("task", "t", []string{}, "Task name")
	mockCmd.AddCommand(mockBuildCmd)
}
