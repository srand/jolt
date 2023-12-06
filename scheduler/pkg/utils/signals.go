package utils

import (
	"fmt"
	"os"
	"os/signal"
	"runtime"
	"syscall"
)

func init() {
	// Register a signal handler for SIGUSR1 that
	// prints the stack trace of all goroutines

	ch := make(chan os.Signal, 10)
	signal.Notify(ch, syscall.SIGUSR1)

	go func() {
		for sig := range ch {
			switch sig {
			case syscall.SIGUSR1:
				buf := make([]byte, 1<<16)
				len := runtime.Stack(buf, true)
				fmt.Printf("%s\n", buf[:len])
			}

		}
	}()
}

// Terminates the process when SIGTERM is received.
func TerminateOnSignal() {
	ch := make(chan os.Signal, 10)
	signal.Notify(ch, syscall.SIGTERM)

	go func() {
		sig := <-ch

		// Exit with the signal number + 128
		os.Exit(int(sig.(syscall.Signal)) + 128)
	}()
}
