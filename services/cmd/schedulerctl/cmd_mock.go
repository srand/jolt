package main

import "github.com/spf13/cobra"

var mockCmd = &cobra.Command{
	Use:   "mock",
	Short: "Schedule build or task with scheduler service",
}

func init() {
	rootCmd.AddCommand(mockCmd)
}
