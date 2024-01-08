package main

import (
	"fmt"
	"log"
	"os"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var rootCmd = &cobra.Command{
	Use:   "schedulerctl",
	Short: "Scheduler control command",
}

var configData = ControlConfig{}

func main() {
	rootCmd.PersistentFlags().StringP("scheduler-uri", "s", "tcp://scheduler:9090", "Scheduler service URI")
	viper.BindPFlag("scheduler_uri", rootCmd.PersistentFlags().Lookup("scheduler-uri"))

	viper.SetEnvPrefix("jolt")
	viper.AutomaticEnv()

	viper.SetConfigName("schedulerctl.yaml")
	viper.SetConfigType("yaml")
	viper.AddConfigPath("/etc/jolt/")
	viper.AddConfigPath("$HOME/.config/jolt")
	viper.AddConfigPath(".")
	viper.ReadInConfig()

	config, err := LoadConfig()
	if err != nil {
		log.Fatal(err)
	}
	configData = *config

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
