package utils

import (
	"fmt"
	"os"
	"os/signal"
	"runtime"
	"syscall"
)

func init() {
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
