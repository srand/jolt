package utils

import (
	"testing"

	"github.com/stretchr/testify/assert"
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
