package main

import "github.com/spf13/cobra"

var buildCmd = &cobra.Command{
	Use:   "build",
	Short: "Commands to inspect and manipulate builds",
}

func init() {
	rootCmd.AddCommand(buildCmd)
}
