package utils

import (
	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/log"
)

type BroadcastConsumer[E any] struct {
	Chan      chan E
	ID        string
	Broadcast *Broadcast[E]
	err       error
}

type Broadcast[E any] struct {
	mu        RWMutex
	consumers map[string]*BroadcastConsumer[E]
	closed    bool
}

func NewBroadcast[E any]() *Broadcast[E] {
	return &Broadcast[E]{
		mu:        NewRWMutex(),
		consumers: map[string]*BroadcastConsumer[E]{},
	}
}

func (bc *Broadcast[E]) Lock() {
	bc.mu.Lock()
}

func (bc *Broadcast[E]) Unlock() {
	bc.mu.Unlock()
}

func (bc *Broadcast[E]) RLock() {
	bc.mu.RLock()
}

func (bc *Broadcast[E]) RUnlock() {
	bc.mu.RUnlock()
}

func (bc *Broadcast[E]) NewConsumer() *BroadcastConsumer[E] {
	uuid, _ := uuid.NewRandom()
	consumer := &BroadcastConsumer[E]{
		Chan:      make(chan E, 100),
		ID:        uuid.String(),
		Broadcast: bc,
	}
	bc.Lock()
	defer bc.Unlock()
	if bc.closed {
		close(consumer.Chan)
		return consumer
	}
	bc.consumers[consumer.ID] = consumer
	return consumer
}

func (bc *Broadcast[E]) HasConsumer() bool {
	bc.RLock()
	defer bc.RUnlock()
	return len(bc.consumers) > 0
}

func (bc *Broadcast[E]) Close() {
	bc.Lock()
	defer bc.Unlock()
	if bc.closed {
		return
	}
	bc.closed = true

	for _, consumer := range bc.consumers {
		close(consumer.Chan)
	}

	bc.consumers = nil
}

func (bc *Broadcast[E]) Remove(bcc *BroadcastConsumer[E]) bool {
	bc.Lock()
	defer bc.Unlock()
	consumer, ok := bc.consumers[bcc.ID]
	if !ok || consumer != bcc {
		return false
	}
	delete(bc.consumers, bcc.ID)
	return true
}

func (bcc *BroadcastConsumer[E]) Close() {
	bc := bcc.Broadcast
	bc.Lock()
	defer bc.Unlock()
	bc.closeConsumer(bcc, nil)
}

// Err reports why the consumer was disconnected. A normal close has no error.
func (bcc *BroadcastConsumer[E]) Err() error {
	bcc.Broadcast.RLock()
	defer bcc.Broadcast.RUnlock()
	return bcc.err
}

// closeConsumer removes and closes a consumer. The caller must hold bc's write lock.
func (bc *Broadcast[E]) closeConsumer(bcc *BroadcastConsumer[E], err error) bool {
	consumer, ok := bc.consumers[bcc.ID]
	if !ok || consumer != bcc {
		return false
	}
	delete(bc.consumers, bcc.ID)
	bcc.err = err
	close(bcc.Chan)
	return true
}

func (bc *Broadcast[E]) Send(data E) {
	var overflowed []string

	bc.Lock()
	if bc.closed {
		bc.Unlock()
		return
	}
	for _, c := range bc.consumers {
		select {
		case c.Chan <- data:
		default:
			if bc.closeConsumer(c, ErrBroadcastConsumerOverflow) {
				overflowed = append(overflowed, c.ID)
			}
		}
	}
	bc.Unlock()

	for _, id := range overflowed {
		log.Debugf("disconnecting broadcast consumer %s: channel full", id)
	}
}
