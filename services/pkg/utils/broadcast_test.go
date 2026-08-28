package utils

import (
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

var broadcastTestData = "testing"

func TestBroadcast(t *testing.T) {
	bc := NewBroadcast[string]()
	c1 := bc.NewConsumer()
	c2 := bc.NewConsumer()
	bc.Send(broadcastTestData)

	msg := <-c1.Chan
	assert.NotNil(t, msg)
	assert.Equal(t, broadcastTestData, msg)

	msg = <-c2.Chan
	assert.NotNil(t, msg)
	assert.Equal(t, broadcastTestData, msg)

}

func TestBroadcastFullConsumerDoesNotBlock(t *testing.T) {
	bc := NewBroadcast[string]()
	consumer := bc.NewConsumer()
	for range cap(consumer.Chan) {
		consumer.Chan <- broadcastTestData
	}

	done := make(chan struct{})
	go func() {
		bc.Send("dropped")
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("broadcast blocked on a full consumer")
	}
	require.False(t, bc.HasConsumer())
	require.ErrorIs(t, consumer.Err(), ErrBroadcastConsumerOverflow)
	for range consumer.Chan {
	}
}

func TestBroadcastFullConsumerDoesNotBlockOthers(t *testing.T) {
	bc := NewBroadcast[string]()
	full := bc.NewConsumer()
	for range cap(full.Chan) {
		full.Chan <- broadcastTestData
	}
	receiver := bc.NewConsumer()

	bc.Send("delivered")

	select {
	case msg := <-receiver.Chan:
		assert.Equal(t, "delivered", msg)
	case <-time.After(time.Second):
		t.Fatal("full consumer prevented delivery to another consumer")
	}
	require.True(t, bc.HasConsumer())
	require.ErrorIs(t, full.Err(), ErrBroadcastConsumerOverflow)
}

func TestBroadcastCloseIsNormalAndIdempotent(t *testing.T) {
	bc := NewBroadcast[string]()
	consumer := bc.NewConsumer()

	bc.Close()
	bc.Close()
	consumer.Close()

	_, ok := <-consumer.Chan
	require.False(t, ok)
	require.NoError(t, consumer.Err())

	lateConsumer := bc.NewConsumer()
	_, ok = <-lateConsumer.Chan
	require.False(t, ok)
	require.NoError(t, lateConsumer.Err())
}

func TestBroadcastOverflowIsRetryable(t *testing.T) {
	err := GrpcError(ErrBroadcastConsumerOverflow)
	require.Equal(t, codes.Unavailable, status.Code(err))
}

func TestBroadcastConcurrentSendAndConsumerClose(t *testing.T) {
	for range 1000 {
		bc := NewBroadcast[int]()
		consumer := bc.NewConsumer()

		var wg sync.WaitGroup
		wg.Add(2)
		go func() {
			defer wg.Done()
			bc.Send(1)
		}()
		go func() {
			defer wg.Done()
			consumer.Close()
		}()
		wg.Wait()
	}
}
