package utils

import (
	"regexp"
	"runtime"
	"strconv"
	"sync"
	"time"
)

type mutexLockInfo struct {
	stack string
	count int
}

type RWMutex struct {
	// Main mutex
	mu sync.RWMutex

	// Mutex to protect the info map
	infoMu sync.Mutex

	// Info about the lockers
	info map[int]*mutexLockInfo

	// Current owner of the lock
	owner int

	// Timeout for the lock
	timeout time.Duration
}

// NewRWMutex creates a new RWMutex with the given timeout.
func NewRWMutex() *RWMutex {
	return &RWMutex{
		info:    make(map[int]*mutexLockInfo),
		timeout: 30 * time.Second,
	}
}

func (m *RWMutex) getStack() string {
	bytes := make([]byte, 0x10000)
	n := runtime.Stack(bytes, false)
	return string(bytes[:n])
}

func (m *RWMutex) getGoroutineID(stack string) int {
	// Use a regex to get the goroutine ID from the stack.
	// The stack is in the following format:
	//
	// goroutine 1 [running]:
	// runtime/pprof.writeGoroutineStacks(0x7f8f5c000000, 0xc0000b8000, 0x0, 0x0)
	// 	/usr/local/go/src/runtime/pprof/pprof.go:694 +0x9d

	regexp := regexp.MustCompile(`goroutine (\d+)`)
	match := regexp.FindStringSubmatch(stack)
	if len(match) > 1 {
		// The goroutine ID is the first capture group
		// Convert it to an integer
		id, _ := strconv.Atoi(match[1])
		return id
	}

	panic("could not find goroutine ID")
}

func (m *RWMutex) dumpInfo() {
	m.infoMu.Lock()
	defer m.infoMu.Unlock()

	println("=====================================================================")
	println("Current mutex owner:", m.owner)
	println("=====================================================================")

	for _, info := range m.info {
		println(info.stack)
		println("=====================================================================")
	}
}

func (m *RWMutex) makeInfo() (*mutexLockInfo, int) {
	stack := m.getStack()
	goroutineID := m.getGoroutineID(stack)

	return &mutexLockInfo{
		stack: stack,
		count: 1,
	}, goroutineID
}

// Lock locks the mutex and sets the owner to the current goroutine.
func (m *RWMutex) Lock() {
	m.infoMu.Lock()
	info, id := m.makeInfo()
	if _, ok := m.info[id]; ok {
		m.infoMu.Unlock()
		m.dumpInfo()
		panic("attempted to lock a mutex that is already locked")
	}
	m.info[id] = info
	m.infoMu.Unlock()

	locked := make(chan struct{})
	go func() {
		m.mu.Lock()
		m.owner = id
		locked <- struct{}{}
	}()

	select {
	case <-locked:
		return
	case <-time.After(m.timeout):
		m.dumpInfo()
		panic("deadlock timeout")
	}
}

// Unlock unlocks the mutex and resets the owner.
func (m *RWMutex) Unlock() {
	_, id := m.makeInfo()
	m.infoMu.Lock()
	delete(m.info, id)
	m.infoMu.Unlock()

	m.owner = 0
	m.mu.Unlock()
}

// TryLock tries to lock the mutex and returns true if it was successful.
func (m *RWMutex) TryLock() bool {
	m.infoMu.Lock()
	info, id := m.makeInfo()
	if _, ok := m.info[id]; ok {
		m.infoMu.Unlock()
		m.dumpInfo()
		panic("attempted to lock a mutex that is already locked")
	}
	m.info[id] = info
	m.infoMu.Unlock()

	locked := make(chan struct{})
	go func() {
		if m.mu.TryLock() {
			m.owner = id
			locked <- struct{}{}
		} else {
			locked <- struct{}{}
		}
	}()

	select {
	case <-locked:
		return m.owner == id
	case <-time.After(m.timeout):
		m.dumpInfo()
		panic("deadlock timeout")
	}
}

// RLock locks the mutex for reading and sets the owner to the current goroutine.
func (m *RWMutex) RLock() {
	m.infoMu.Lock()
	info, id := m.makeInfo()
	if info, ok := m.info[id]; ok {
		info.count++
		m.infoMu.Unlock()
		return
	}
	m.info[id] = info
	m.infoMu.Unlock()

	locked := make(chan struct{})
	go func() {
		m.mu.RLock()
		m.owner = id
		locked <- struct{}{}
	}()

	select {
	case <-locked:
		return
	case <-time.After(m.timeout):
		m.dumpInfo()
		panic("deadlock timeout")
	}
}

// RUnlock unlocks the mutex and resets the owner.
func (m *RWMutex) RUnlock() {
	_, id := m.makeInfo()
	m.infoMu.Lock()
	info := m.info[id]
	if info.count > 1 {
		info.count--
		m.infoMu.Unlock()
		return
	}
	delete(m.info, id)
	m.infoMu.Unlock()

	m.owner = 0
	m.mu.RUnlock()
}
