package main

import (
	"context"
	"fmt"
	"net/http"
	"os"

	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/logstash"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
	"github.com/srand/jolt/scheduler/pkg/utils"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var config *Config

var rootCmd = &cobra.Command{
	Use:   "scheduler",
	Short: "Jolt remote task execution scheduler service",
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		viper.SetEnvPrefix("jolt")
		viper.AutomaticEnv()

		viper.SetConfigName("scheduler.yaml")
		viper.SetConfigType("yaml")
		viper.AddConfigPath("/etc/jolt/")
		viper.AddConfigPath("$HOME/.config/jolt")
		viper.AddConfigPath(".")

		viper.ReadInConfig()

		if err := utils.UnmarshalConfig(*viper.GetViper(), &config); err != nil {
			log.Fatal(err)
		}

		config.LogStash.SetDefaults()

		if err := config.LogStash.Validate(); err != nil {
			log.Fatal(err)
		}

		config.Log()

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
		ctx := context.Background()

		// Create scheduler.
		sched := scheduler.NewPriorityScheduler()

		// Mirror scheduler state for subscribers of the administration event stream.
		// Must be registered before any listener accepts connections.
		events := scheduler.NewEventHub(config.GetLogstashUri())
		sched.AddObserver(events)
		go events.Run(ctx)

		// Create filesystem storage for the logstash
		stashFs, err := config.LogStash.CreateFs()
		if err != nil {
			log.Fatal(err)
		}

		// Create new logstash
		stash := logstash.NewLogStash(&config.LogStash, stashFs)

		authenticator, err := auth.New(config.Auth, scheduler.Permissions...)
		if err != nil {
			log.Fatal(err)
		}

		// Start listening for Grpc connections on all configured addresses
		schedulerUris := viper.GetStringSlice("listen_grpc")
		for _, uri := range schedulerUris {
			go serveGrpc(sched, events, stash, authenticator, uri)
		}

		// Start listening for logstash HTTP connections on all configured addresses
		logstashUris := viper.GetStringSlice("listen_http")
		for _, uri := range logstashUris {
			host, err := utils.ParseHttpUrl(uri)
			if err != nil {
				log.Fatal(err)
			}

			log.Info("Listening on http", host)

			r := http.NewServeMux()
			r.Handle("GET /debug/pprof/", http.DefaultServeMux)

			logstash.NewHttpHandler(stash, r)
			scheduler.NewHttpHandler(sched, r)

			go http.ListenAndServe(host, utils.HttpLogger(authenticator.HttpHandler(r, scheduler.HttpPermission)))
		}

		// Ready to run the scheduler
		sched.Run(ctx)
	},
}

func init() {
	rootCmd.Flags().StringSliceP("listen-http", "l", []string{"tcp://:8080"}, "Addresses to listen on for HTTP connections")
	rootCmd.Flags().StringSliceP("listen-grpc", "g", []string{"tcp://:9090"}, "Addresses to listen on for GRPC connections")
	rootCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable)")

	viper.BindPFlag("listen_grpc", rootCmd.Flags().Lookup("listen-grpc"))
	viper.BindPFlag("listen_http", rootCmd.Flags().Lookup("listen-http"))
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
