package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/spf13/cobra"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/encoding/protojson"
)

var (
	eventTasks      bool
	eventWorkers    bool
	eventBuilds     bool
	eventBuildId    string
	eventStatuses   []string
	eventLabels     []string
	eventHostname   string
	eventNoSnapshot bool
	eventJson       bool
)

var eventCmd = &cobra.Command{
	Use:   "events",
	Short: "Stream scheduler state changes",
	Long: "Subscribes to the scheduler event stream. Unless --no-snapshot is given, " +
		"the current state of all queued and running tasks and all connected " +
		"workers and registered builds is printed first, followed by incremental updates. " +
		"Select --tasks, --workers and/or --builds to limit event kinds.",
	Run: func(cmd *cobra.Command, args []string) {
		statuses, err := parseTaskStatuses(eventStatuses)
		if err != nil {
			log.Fatal(err)
		}

		request := &protocol.StreamEventsRequest{
			Tasks:      eventTasks,
			Workers:    eventWorkers,
			Builds:     eventBuilds,
			BuildId:    eventBuildId,
			TaskStatus: statuses,
			Labels:     eventLabels,
			Hostname:   eventHostname,
			NoSnapshot: eventNoSnapshot,
		}

		ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer cancel()

		client := NewAdminClient()
		stream, err := client.StreamEvents(ctx, request, grpc.MaxCallRecvMsgSize(32*10e6))
		if err != nil {
			log.Fatal(err)
		}

		for {
			event, err := stream.Recv()
			if err == io.EOF || ctx.Err() != nil {
				return
			}
			if err != nil {
				log.Fatal(err)
			}

			if eventJson {
				printEventJson(event)
			} else {
				printEvent(event)
			}
		}
	},
}

func parseTaskStatuses(names []string) ([]protocol.TaskStatus, error) {
	statuses := make([]protocol.TaskStatus, 0, len(names))

	for _, name := range names {
		key := strings.ToUpper(name)
		if !strings.HasPrefix(key, "TASK_") {
			key = "TASK_" + key
		}

		value, ok := protocol.TaskStatus_value[key]
		if !ok {
			return nil, fmt.Errorf("unknown task status: %s", name)
		}

		statuses = append(statuses, protocol.TaskStatus(value))
	}

	return statuses, nil
}

func printEventJson(event *protocol.SchedulerEvent) {
	data, err := protojson.Marshal(event)
	if err != nil {
		log.Fatal(err)
	}

	// protojson deliberately produces unstable whitespace; normalize it.
	var compact bytes.Buffer
	if err := json.Compact(&compact, data); err != nil {
		log.Fatal(err)
	}

	fmt.Fprintln(os.Stdout, compact.String())
}

func printEvent(event *protocol.SchedulerEvent) {
	switch e := event.GetEvent().(type) {
	case *protocol.SchedulerEvent_Snapshot:
		snapshot := e.Snapshot
		fmt.Printf("snapshot   %s tasks: %d, workers: %d, builds: %d\n",
			snapshot.GetTimestamp().AsTime().Format("15:04:05.000"),
			len(snapshot.GetTasks()),
			len(snapshot.GetWorkers()),
			len(snapshot.GetBuilds()),
		)
		for _, task := range snapshot.GetTasks() {
			printTask("task      ", task)
		}
		for _, worker := range snapshot.GetWorkers() {
			printWorker("worker    ", worker)
		}
		for _, build := range snapshot.GetBuilds() {
			printBuild(build)
		}

	case *protocol.SchedulerEvent_Task:
		printTask("task      ", e.Task)

	case *protocol.SchedulerEvent_Worker:
		printWorker("worker    ", e.Worker)

	case *protocol.SchedulerEvent_WorkerRemoved:
		fmt.Printf("delisted   %s\n", e.WorkerRemoved.GetId())

	case *protocol.SchedulerEvent_Heartbeat:
		fmt.Printf("heartbeat  %s\n", e.Heartbeat.AsTime().Format("15:04:05.000"))
	case *protocol.SchedulerEvent_Build:
		printBuild(e.Build)
	case *protocol.SchedulerEvent_BuildRemoved:
		fmt.Printf("removed    build %s\n", e.BuildRemoved.GetId())
	}
}

func printBuild(build *protocol.BuildInfo) {
	fmt.Printf("build      %-14s %s scheduled: %s",
		strings.TrimPrefix(build.GetStatus().String(), "BUILD_"), build.GetId(),
		build.GetScheduledAt().AsTime().Format("15:04:05.000"))
	for _, param := range build.GetParameters() {
		fmt.Printf(" %s=%q", param.GetKey(), param.GetValue())
	}
	fmt.Println()
}

func printTask(prefix string, task *protocol.TaskInfo) {
	fmt.Printf("%s %-14s %s %s",
		prefix,
		strings.TrimPrefix(task.GetStatus().String(), "TASK_"),
		task.GetInstance(),
		task.GetName(),
	)

	if hostname := task.GetWorkerHostname(); hostname != "" {
		fmt.Printf(" @%s", hostname)
	}
	if labels := task.GetLabels(); len(labels) > 0 {
		fmt.Printf(" [%s]", strings.Join(labels, ","))
	}
	fmt.Println()
}

// Worker events are upserts, so report the worker's state rather than an event name.
func printWorker(prefix string, worker *protocol.WorkerInfo) {
	task := worker.GetTask()

	state := "IDLE"
	if task != nil {
		state = strings.TrimPrefix(task.GetStatus().String(), "TASK_")
	}

	fmt.Printf("%s %-14s %s", prefix, state, worker.GetId())

	if hostname := worker.GetHostname(); hostname != "" {
		fmt.Printf(" @%s", hostname)
	}
	if task != nil {
		fmt.Printf(" %s", task.GetName())
	}
	fmt.Println()
}

func init() {
	eventCmd.Flags().BoolVar(&eventTasks, "tasks", false, "Only stream task events (all kinds if none selected)")
	eventCmd.Flags().BoolVar(&eventWorkers, "workers", false, "Only stream worker events (all kinds if none selected)")
	eventCmd.Flags().BoolVar(&eventBuilds, "builds", false, "Only stream build events (all kinds if none selected)")
	eventCmd.Flags().StringVarP(&eventBuildId, "build", "b", "", "Only stream events for this build")
	eventCmd.Flags().StringSliceVar(&eventStatuses, "status", nil, "Only stream tasks with these statuses, e.g. queued,running")
	eventCmd.Flags().StringSliceVarP(&eventLabels, "label", "L", nil, "Only stream tasks and workers with all of these labels")
	eventCmd.Flags().StringVar(&eventHostname, "hostname", "", "Only stream tasks and workers on this host")
	eventCmd.Flags().BoolVar(&eventNoSnapshot, "no-snapshot", false, "Do not print the initial state snapshot")
	eventCmd.Flags().BoolVar(&eventJson, "json", false, "Print events as JSON, one per line")

	rootCmd.AddCommand(eventCmd)
}
