//go:build windows

package utils

import (
	"errors"
	"io"
	"os"
	"os/exec"
)

type Command struct {
	cmd *exec.Cmd
}

func NewCommand(args ...string) *Command {
	cmd := exec.Command(args[0], args[1:]...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return &Command{cmd: cmd}
}

func (c *Command) Start() error {
	return c.cmd.Start()
}

func (c *Command) Wait() error {
	return c.cmd.Wait()
}

func (c *Command) WaitChild() error {
	return errors.New("WaitChild not supported on Windows")
}

func (c *Command) Interrupt() error {
	return c.Process().Signal(os.Interrupt)
}

func (c *Command) Kill() error {
	return c.cmd.Process.Kill()
}

func (c *Command) SetStderr(w io.Writer) {
	c.cmd.Stderr = w
}

func (c *Command) SetDir(dir string) {
	c.cmd.Dir = dir
}

func (c *Command) Args() []string {
	return c.cmd.Args
}

func (c *Command) GetPid() int {
	return c.cmd.Process.Pid
}

func (c *Command) Process() *os.Process {
	return c.cmd.Process
}
