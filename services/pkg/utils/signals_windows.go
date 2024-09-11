//go:build windows
package utils

// Terminates the process when SIGTERM is received.
// Not implemented for Windows
func TerminateOnSignal() {
}
