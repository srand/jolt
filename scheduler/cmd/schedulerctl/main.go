package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var rootCmd = &cobra.Command{
	Use:   "schedulerctl",
	Short: "Scheduler control command",
}

func main() {
	rootCmd.PersistentFlags().StringP("scheduler", "s", "scheduler:9090", "Address of scheduler service")
	viper.BindPFlag("scheduler", rootCmd.PersistentFlags().Lookup("scheduler"))

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
