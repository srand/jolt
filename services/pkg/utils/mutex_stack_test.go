package utils

import (
	"testing"
)

func TestGetStack(t *testing.T) {
	m := NewRWMutex()

	stack := m.getStack()
	if stack == "" {
		t.Error("Expected stack to be non-empty")
	}
}

func TestGetGoroutineID(t *testing.T) {
	m := NewRWMutex()

	stack := "goroutine 1 [running]:\n" +
		"runtime/pprof.writeGoroutineStacks(0x7f8f5c000000, 0xc0000b8000, 0x0, 0x0)\n" +
		"	/usr/local/go/src/runtime/pprof/pprof.go:694 +0x9d\n"

	id := m.getGoroutineID(stack)
	if id != 1 {
		t.Errorf("Expected goroutine ID to be 1, got %v", id)
	}
}

func TestRWMutex(t *testing.T) {
	m := NewRWMutex()

	// Lock the mutex
	m.Lock()
	defer m.Unlock()

	// Check that the mutex is locked
	if !m.TryLock() {
		t.Error("Expected mutex to be locked")
	}
}

func TestRWMutexUnlock(t *testing.T) {
	m := NewRWMutex()

	// Lock the mutex
	m.Lock()

	// Unlock the mutex
	m.Unlock()

	// Check that the mutex is unlocked
	if !m.TryLock() {
		t.Error("Expected mutex to be unlocked")
	}

}

func TestRWMutexRLock(t *testing.T) {
	m := NewRWMutex()

	// Lock the mutex
	m.RLock()
	defer m.RUnlock()

	// Check that the mutex is locked
	if m.mu.TryLock() {
		t.Error("Expected mutex to be locked")
	}
}

func TestRWMutexRUnlock(t *testing.T) {
	m := NewRWMutex()

	// Lock the mutex
	m.RLock()

	// Unlock the mutex
	m.RUnlock()

	// Check that the mutex is unlocked
	if !m.TryLock() {
		t.Error("Expected mutex to be unlocked")
	}
}
