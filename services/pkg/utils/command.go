package utils

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"syscall"

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

func Run(args ...string) (chan error, *os.Process, error) {
	return RunOptions("", args...)
}

func RunOptions(cwd string, args ...string) (chan error, *os.Process, error) {
	output := bytes.Buffer{}

	cmd := exec.Command(args[0], args[1:]...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = io.MultiWriter(os.Stderr, &output)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true, Pgid: 0}
	if cwd != "" {
		cmd.Dir = cwd
	}

	log.Info("Running", strings.Join(cmd.Args, " "))

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

	return done, cmd.Process, nil
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
