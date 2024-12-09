package utils

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/srand/jolt/scheduler/pkg/log"
)

type commandError struct {
	message string
	details string
}

func NewCmdError(message, details string) error {
	return &commandError{
		message: message,
		details: details,
	}
}

func (c *commandError) Details() string {
	return c.details
}

func (c *commandError) Error() string {
	return c.message
}

func Run(args ...string) (chan error, *Command, error) {
	return RunOptions("", args...)
}

func RunOptions(cwd string, args ...string) (chan error, *Command, error) {
	output := bytes.Buffer{}

	cmd := NewCommand(args...)
	cmd.SetStderr(io.MultiWriter(os.Stderr, &output))
	if cwd != "" {
		cmd.SetDir(cwd)
	}

	log.Info("Running", strings.Join(cmd.Args(), " "))

	if err := cmd.Start(); err != nil {
		return nil, nil, err
	}

	done := make(chan error)
	go func() {
		err := cmd.Wait()
		if err != nil {
			message := fmt.Sprintf("Command failed: %s (%v)", strings.Join(args, " "), err)
			log.Error(message)
			done <- NewCmdError(message, output.String())
		}
		close(done)
	}()

	return done, cmd, nil
}

func RunWait(args ...string) error {
	done, _, err := Run(args...)
	if err != nil {
		return err
	}
	return <-done
}

func RunWaitCwd(cwd string, args ...string) error {
	done, _, err := RunOptions(cwd, args...)
	if err != nil {
		return err
	}
	return <-done
}
