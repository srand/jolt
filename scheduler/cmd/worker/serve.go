package main

import (
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
	"github.com/srand/jolt/scheduler/pkg/worker"
)

func Serve(cmd *cobra.Command, args []string) {
	verbosity, err := cmd.Flags().GetCount("verbose")
	if err != nil {
		panic(err)
	}
	switch {
	case verbosity >= 2:
		log.SetLevel(log.TraceLevel)
	case verbosity >= 1:
		log.SetLevel(log.DebugLevel)
	}

	platform := scheduler.NewPlatformWithDefaults()
	platform.LoadConfig()
	log.Info("Properties:")
	for _, prop := range platform.Properties {
		log.Infof("  %s=%s", prop.Key, prop.Value)
	}

	workerClient, err := worker.NewWorkerClient(viper.GetString("scheduler"))
	if err != nil {
		panic(err)
	}

	worker := worker.NewWorker(platform, workerClient)
	worker.Run()
}
