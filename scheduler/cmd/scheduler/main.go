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
	rootCmd.Flags().IntP("port", "p", 9090, "TCP port to run scheduler on")
	rootCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable)")

	viper.BindPFlag("port", rootCmd.Flags().Lookup("port"))
	viper.SetEnvPrefix("jolt")
	viper.AutomaticEnv()

	viper.SetConfigName("scheduler.yaml")
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
