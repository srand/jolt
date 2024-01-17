package main

import (
	"context"
	"fmt"
	"os"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/logstash"
	"github.com/srand/jolt/scheduler/pkg/scheduler"

	"github.com/spf13/afero"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var config Config

var rootCmd = &cobra.Command{
	Use:   "scheduler",
	Short: "Jolt remote task execution scheduler service",
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		viper.BindPFlag("grpc_listen", cmd.Flags().Lookup("listen-grpc"))
		viper.BindPFlag("http_listen", cmd.Flags().Lookup("listen-http"))

		viper.SetEnvPrefix("jolt")
		viper.AutomaticEnv()

		viper.SetConfigName("scheduler.yaml")
		viper.SetConfigType("yaml")
		viper.AddConfigPath("/etc/jolt/")
		viper.AddConfigPath("$HOME/.config/jolt")
		viper.AddConfigPath(".")

		viper.ReadInConfig()

		if err := viper.Unmarshal(&config); err != nil {
			log.Fatal(err)
		}

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
	},
	Run: func(cmd *cobra.Command, args []string) {

		// Create scheduler.
		sched := scheduler.NewPriorityScheduler()

		// Create filesystem storage for the logstash
		stashFs, err := config.LogStash.CreateFs()
		if err != nil {
			log.Fatal(err)
		}

		afero.WriteFile(stashFs, "asdf", []byte("here is the log"), 0666)

		// Create new logstash
		stash := logstash.NewLogStash(&config.LogStash, stashFs)

		// Start listening for Grpc connections on all configured addresses
		schedulerUris := viper.GetStringSlice("grpc_listen")
		for _, uri := range schedulerUris {
			go serveGrpc(sched, stash, uri)
		}

		// Start listening for logstash HTTP connections on all configured addresses
		logstashUris := viper.GetStringSlice("http_listen")
		for _, uri := range logstashUris {
			go serveHttp(stash, uri)
		}

		// Ready to run the scheduler
		sched.Run(context.Background())
	},
}

func init() {
	rootCmd.Flags().StringSliceP("listen-http", "l", []string{"tcp://:8080"}, "Addresses to listen on for HTTP connections")
	rootCmd.Flags().StringSliceP("listen-grpc", "g", []string{"tcp://:9090"}, "Addresses to listen on for GRPC connections")
	rootCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable)")
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
