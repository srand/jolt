package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var rootCmd = &cobra.Command{
	Use:   "scheduler",
	Short: "Jolt remote task execution scheduler service",
	Run:   Serve,
}

func main() {
	rootCmd.Flags().IntP("port", "p", 9091, "TCP port to listen on")
	rootCmd.Flags().StringP("scheduler", "s", "scheduler:9090", "Address of scheduler service")
	rootCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable)")

	viper.BindPFlag("port", rootCmd.Flags().Lookup("port"))
	viper.BindPFlag("scheduler", rootCmd.Flags().Lookup("scheduler"))
	viper.SetEnvPrefix("jolt")
	viper.AutomaticEnv()

	viper.SetConfigName("worker.yaml")
	viper.SetConfigType("yaml")
	viper.AddConfigPath("/etc/jolt/")
	viper.AddConfigPath("$HOME/.config/jolt")
	viper.AddConfigPath(".")
	viper.ReadInConfig()

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
