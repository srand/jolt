//go:build linux

package utils

import (
	"io"
	"os"
	"os/exec"
	"syscall"
)

type Command struct {
	cmd *exec.Cmd
}

func NewCommand(args ...string) *Command {
	cmd := exec.Command(args[0], args[1:]...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true, Pgid: 0}
	return &Command{cmd: cmd}
}

func (c *Command) Start() error {
	return c.cmd.Start()
}

func (c *Command) Wait() error {
	return c.cmd.Wait()
}

func (c *Command) WaitChild() error {
	_, err := syscall.Wait4(-c.GetPid(), nil, 0, nil)
	return err
}

func (c *Command) Interrupt() error {
	return c.Process().Signal(os.Interrupt)
}

func (c *Command) Kill() error {
	return syscall.Kill(-c.GetPid(), syscall.SIGKILL)
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
