package utils

import (
	"context"
	"slices"
	"sync"

	"github.com/google/uuid"
	"github.com/srand/jolt/scheduler/pkg/log"
)

type UnicastConsumer[E comparable] struct {
	Chan    chan E
	ID      string
	cancel  func()
	ctx     context.Context
	owner   interface{}
	unicast *Unicast[E]
}

// Callback when iterating items in the queue.
// Return true to continue iteration, or false to stop.
type UnicastWalkFunc[E comparable] func(unicast *Unicast[E], item E) bool

// Callback to select the next item to be delivered to a consumer.
// Return true to select the current item, or false to evaluate the next item.
type UnicastSelectionFunc[E comparable] func(item E, consumer interface{}) bool

// A reliable unicast queue.
// Items added to the queue are delivered to a single consumer.
// The consumer must acknowledge that the item has been received and handled,
// otherwise the item is delivered to another consumer if the original consumer
// unsubscribes from the queue. There is no deadline for consumers to acknowledge
// an item.
type Unicast[E comparable] struct {
	sync.RWMutex

	// All consumers
	// Indexed by consumer ID.
	consumers map[string]*UnicastConsumer[E]

	// Consumers that are available to receive an item,
	// i.e. have no outstanding item to acknowledge.
	// Indexed by consumer ID.
	availConsumers map[string]*UnicastConsumer[E]

	// Items delivered to a consumer but not yet acknowledged by the consumer.
	// Indexed by consumer ID.
	consumerItem map[string]E

	// All items in the queue. New items are appended to the list.
	queue []E

	// Next item selection function.
	selectionFn UnicastSelectionFunc[E]
}

func NewUnicast[E comparable](selectionFn UnicastSelectionFunc[E]) *Unicast[E] {
	return &Unicast[E]{
		consumers:      map[string]*UnicastConsumer[E]{},
		availConsumers: map[string]*UnicastConsumer[E]{},
		consumerItem:   map[string]E{},
		queue:          []E{},
		selectionFn:    selectionFn,
	}
}

// Close the unicast and cancel all consumers.
func (bc *Unicast[E]) Close() {
	bc.Lock()
	defer bc.Unlock()

	for _, consumer := range bc.consumers {
		consumer.cancel()
	}
}

// Create a new consumer.
func (bc *Unicast[E]) NewConsumer(owner interface{}) *UnicastConsumer[E] {
	ctx, cancel := context.WithCancel(context.Background())
	uuid, _ := uuid.NewRandom()
	consumer := &UnicastConsumer[E]{
		Chan:    make(chan E, 100),
		ID:      uuid.String(),
		ctx:     ctx,
		cancel:  cancel,
		unicast: bc,
		owner:   owner,
	}
	bc.Lock()
	defer bc.Unlock()
	bc.consumers[consumer.ID] = consumer
	bc.availConsumers[consumer.ID] = consumer
	bc.send()
	return consumer
}

// Returns true if there are delivered items that have not yet been acknowledged.
func (bc *Unicast[E]) HasUnackedData() bool {
	bc.Lock()
	defer bc.Unlock()
	return len(bc.consumerItem) > 0
}

// Number of items that have been delivered but not yet acknowledged.
func (bc *Unicast[E]) NumUnackedData() int {
	bc.Lock()
	defer bc.Unlock()
	return len(bc.consumerItem)
}

func (bc *Unicast[E]) acknowledge(bcc *UnicastConsumer[E]) {
	bc.Lock()
	defer bc.Unlock()
	bc.availConsumers[bcc.ID] = bcc
	delete(bc.consumerItem, bcc.ID)
	bc.send()
}

func (bc *Unicast[E]) send() {
	if len(bc.queue) == 0 {
		return
	}

	if len(bc.availConsumers) == 0 {
		return
	}

	for _, bcc := range bc.availConsumers {
		for i, data := range bc.queue {
			if bc.selectionFn(data, bcc.owner) {
				bc.queue = append(bc.queue[:i], bc.queue[i+1:]...)
				delete(bc.availConsumers, bcc.ID)
				bc.consumerItem[bcc.ID] = data
				bcc.send(data)
				return
			}
		}
	}
}

// Returns true if the unicast queue is empty.
func (bc *Unicast[E]) Empty() bool {
	bc.Lock()
	defer bc.Unlock()
	return len(bc.queue) == 0
}

// Returns the number of items in the queue.
func (bc *Unicast[E]) Len() int {
	bc.Lock()
	defer bc.Unlock()
	return len(bc.queue)
}

func (bc *Unicast[E]) remove(bcc *UnicastConsumer[E]) {
	bc.Lock()
	defer bc.Unlock()
	delete(bc.consumers, bcc.ID)
	delete(bc.availConsumers, bcc.ID)
	if data, ok := bc.consumerItem[bcc.ID]; ok {
		delete(bc.consumerItem, bcc.ID)
		bc.queue = append(bc.queue, data)
		bc.send()
	}
}

// Add item to queue.
func (bc *Unicast[E]) Send(data E) {
	bc.Lock()
	defer bc.Unlock()

	// Don't add duplicate items to the queue.
	if slices.Contains[[]E, E](bc.queue, data) {
		return
	}

	// Item may also have been delivered to a consumer but not yet acknowledged.
	// FIXME: Possible performance issue if many consumers are available.
	for _, item := range bc.consumerItem {
		if item == data {
			return
		}
	}

	bc.queue = append(bc.queue, data)
	bc.send()
}

// Iterate through all items in the queue,
// including those delivered but now yet acknowledged.
func (bc *Unicast[E]) Walk(walker UnicastWalkFunc[E]) bool {
	bc.RLock()
	defer bc.RUnlock()
	for _, item := range bc.queue {
		if !walker(bc, item) {
			return false
		}
	}

	return true
}

// Acknowledge that item has been handled.
func (bcc *UnicastConsumer[E]) Acknowledge() {
	bcc.unicast.acknowledge(bcc)
}

// Close the consumer and unregister from the unicast.
func (bcc *UnicastConsumer[E]) Close() {
	bcc.cancel()
	bcc.unicast.remove(bcc)
	close(bcc.Chan)
}

// Channel indicating that the consumer is cancelled
// and no longer will be receiving items.
func (bcc *UnicastConsumer[E]) Done() <-chan struct{} {
	return bcc.ctx.Done()
}

func (bcc *UnicastConsumer[E]) send(data E) error {
	select {
	case bcc.Chan <- data:
		return nil
	default:
		log.Debugf("Unable to send event to %s, channel full", bcc.ID)
	}

	bcc.Chan <- data
	return nil
}
