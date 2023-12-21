package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/srand/jolt/scheduler/pkg/worker"
)

var rootCmd = &cobra.Command{
	Use:   "scheduler",
	Short: "Jolt remote task execution scheduler service",
	Run: func(cmd *cobra.Command, args []string) {
		verbosity, err := cmd.Flags().GetCount("verbose")
		if err != nil {
			log.Fatal(err)
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

		// Load worker configuration from file or environment.
		workerConfig, err := LoadConfig()
		if err != nil {
			log.Fatal(err)
		}

		fmt.Println(workerConfig)

		// Validate the worker configuration.
		if err := workerConfig.Validate(); err != nil {
			log.Fatal(err)
		}

		workerClient, err := worker.NewWorkerClient(workerConfig)
		if err != nil {
			log.Fatal(err)
		}

		worker := worker.NewWorker(platform, workerClient, workerConfig)
		worker.Run()
	},
}

func main() {
	rootCmd.Flags().StringP("cache-uri", "c", "http://cache", "Cache service URI")
	rootCmd.Flags().StringSliceP("platform", "p", []string{}, "Platform property (repeatable)")
	rootCmd.Flags().StringP("scheduler-uri", "s", "tcp://scheduler:9090", "Scheduler service URI")
	rootCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable)")

	viper.BindPFlag("cache_uri", rootCmd.Flags().Lookup("cache-uri"))
	viper.BindPFlag("platform", rootCmd.Flags().Lookup("platform"))
	viper.BindPFlag("scheduler_uri", rootCmd.Flags().Lookup("scheduler-uri"))
	viper.SetEnvPrefix("jolt")
	viper.AutomaticEnv()

	viper.SetConfigName("worker.yaml")
	viper.SetConfigType("yaml")
	viper.AddConfigPath("/etc/jolt/")
	viper.AddConfigPath("$HOME/.config/jolt")
	viper.AddConfigPath(".")
	viper.ReadInConfig()

	utils.TerminateOnSignal()

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
