package main

import (
	"fmt"
	"os"
	"runtime"
	"strings"

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

		// Load worker configuration from file or environment.
		workerConfig, err := LoadConfig()
		if err != nil {
			log.Fatal(err)
		}

		log.Info("Worker configuration:")
		log.Infof("  Cache directory: %s", workerConfig.CacheDir)
		log.Infof("  Cache URI: %s", workerConfig.CacheUri)
		log.Infof("  Cache gRPC URI: %s", workerConfig.CacheGrpcUri)
		log.Infof("  Scheduler URI: %s", workerConfig.SchedulerUri)
		log.Infof("  Thread count: %d", workerConfig.ThreadCount)

		platform := scheduler.NewPlatformWithDefaults()
		platform.LoadConfig()
		log.Info("Properties:")
		for prop := range *platform {
			log.Infof("  %s", prop)
		}

		taskPlatform := scheduler.NewPlatform()
		for _, prop := range viper.GetStringSlice("task_platform") {
			parts := strings.SplitN(prop, "=", 2)
			if len(parts) != 2 {
				log.Fatalf("Invalid task platform property: %s", prop)
			}
			taskPlatform.AddProperty(parts[0], parts[1])
		}
		if len(*taskPlatform) > 0 {
			log.Info("Task properties:")
			for prop := range *taskPlatform {
				log.Infof("  %s", prop)
			}
		}

		// Validate the worker configuration.
		if err := workerConfig.Validate(); err != nil {
			log.Fatal(err)
		}

		workerClient, err := worker.NewWorkerClient(workerConfig)
		if err != nil {
			log.Fatal(err)
		}

		worker := worker.NewWorker(platform, taskPlatform, workerClient, workerConfig)
		worker.Run()
	},
}

func main() {
	rootCmd.Flags().StringP("cache-dir", "d", "", "Cache directory")
	rootCmd.Flags().StringP("cache-uri", "u", "http://cache", "Cache service URI")
	rootCmd.Flags().StringP("cache-grpc-uri", "g", "tcp://cache:9090", "Cache service gRPC URI")
	rootCmd.Flags().StringSlice("nix-keep", []string{}, "Nix environment variables to keep (repeatable)")
	rootCmd.Flags().StringSliceP("platform", "p", []string{}, "Platform property (repeatable)")
	rootCmd.Flags().StringSliceP("task-platform", "t", []string{}, "Task platform property (repeatable)")
	rootCmd.Flags().StringP("scheduler-uri", "s", "tcp://scheduler:9090", "Scheduler service URI")
	rootCmd.Flags().StringP("threads", "j", fmt.Sprint(runtime.NumCPU()), "Maximum thread count")
	rootCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable)")

	viper.BindPFlag("cache_dir", rootCmd.Flags().Lookup("cache-dir"))
	viper.BindPFlag("cache_uri", rootCmd.Flags().Lookup("cache-uri"))
	viper.BindPFlag("cache_grpc_uri", rootCmd.Flags().Lookup("cache-grpc-uri"))
	viper.BindPFlag("nix_keep", rootCmd.Flags().Lookup("nix-keep"))
	viper.BindPFlag("platform", rootCmd.Flags().Lookup("platform"))
	viper.BindPFlag("task_platform", rootCmd.Flags().Lookup("task-platform"))
	viper.BindPFlag("scheduler_uri", rootCmd.Flags().Lookup("scheduler-uri"))
	viper.BindPFlag("threads", rootCmd.Flags().Lookup("threads"))
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
