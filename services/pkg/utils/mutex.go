package utils

type RWMutex interface {
	// Lock locks the mutex.
	Lock()

	// Unlock unlocks the mutex.
	Unlock()

	// RLock locks the mutex for reading.
	RLock()

	// RUnlock unlocks the mutex.
	RUnlock()

	// TryLock tries to lock the mutex.
	TryLock() bool
}
