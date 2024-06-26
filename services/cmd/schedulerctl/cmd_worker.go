package main

import "github.com/spf13/cobra"

var workerCmd = &cobra.Command{
	Use:   "worker",
	Short: "Commands to inspect and manipulate workers",
}

func init() {
	rootCmd.AddCommand(workerCmd)
}
