package utils

import (
	"sync"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/log"
)

type BroadcastConsumer[E any] struct {
	Chan      chan E
	ID        string
	Broadcast *Broadcast[E]
}

type Broadcast[E any] struct {
	sync.RWMutex
	consumers map[string]*BroadcastConsumer[E]
}

func NewBroadcast[E any]() *Broadcast[E] {
	return &Broadcast[E]{
		consumers: map[string]*BroadcastConsumer[E]{},
	}
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
	bc.consumers[consumer.ID] = consumer
	return consumer
}

func (bc *Broadcast[E]) HasConsumer() bool {
	bc.Lock()
	defer bc.Unlock()
	return len(bc.consumers) > 0
}

func (bc *Broadcast[E]) Close() {
	bc.Lock()
	defer bc.Unlock()
	for _, consumer := range bc.consumers {
		close(consumer.Chan)
	}

	bc.consumers = map[string]*BroadcastConsumer[E]{}
}

func (bc *Broadcast[E]) Remove(bcc *BroadcastConsumer[E]) bool {
	bc.Lock()
	defer bc.Unlock()
	_, ok := bc.consumers[bcc.ID]
	delete(bc.consumers, bcc.ID)
	return ok
}

func (bcc *BroadcastConsumer[E]) Close() {
	if bcc.Broadcast.Remove(bcc) {
		close(bcc.Chan)
	}
}

func (bcc *BroadcastConsumer[E]) send(data E) error {
	select {
	case bcc.Chan <- data:
		return nil
	default:
		log.Debugf("Unable to send event to %s, channel full", bcc.ID)
	}

	bcc.Chan <- data
	return nil
}

func (bc *Broadcast[E]) Send(data E) {
	bc.RLock()
	defer bc.RUnlock()
	for _, c := range bc.consumers {
		err := c.send(data)
		if err != nil {
			log.Debug(err.Error())
		}
	}
}
