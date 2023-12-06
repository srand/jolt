package utils

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

var unicastTestData = []string{
	"test1",
	"test2",
	"test3",
}

func TestUnicast(t *testing.T) {
	bc := NewUnicast[string](func(item string, consumer interface{}) bool { return true })
	c1 := bc.NewConsumer(nil)
	c2 := bc.NewConsumer(nil)

	for i := range unicastTestData {
		bc.Send(unicastTestData[i])
	}

	var msg string
	select {
	case msg = <-c1.Chan:
	case msg = <-c2.Chan:
	}
	assert.True(t, unicastTestData[0] == msg || unicastTestData[1] == msg)

	select {
	case msg = <-c1.Chan:
	case msg = <-c2.Chan:
	}
	assert.True(t, unicastTestData[0] == msg || unicastTestData[1] == msg)

	// Close consumers without acknowledging message
	c1.Close()
	c2.Close()

	c3 := bc.NewConsumer(nil)

	expectedOrder := []string{
		unicastTestData[2],
		unicastTestData[0],
		unicastTestData[1],
	}

	for i := range expectedOrder {
		msg := <-c3.Chan
		t.Log(msg)
		assert.NotNil(t, msg)
		assert.Equal(t, expectedOrder[i], msg)
		c3.Acknowledge()
	}
}

func TestUnicastAck(t *testing.T) {
	bc := NewUnicast[string](func(item string, consumer interface{}) bool { return true })
	c1 := bc.NewConsumer(nil)

	for i := range unicastTestData {
		bc.Send(unicastTestData[i])
	}

	expectedOrder := []string{
		unicastTestData[0],
		unicastTestData[1],
		unicastTestData[2],
	}

	for i := range expectedOrder {
		msg := <-c1.Chan
		t.Log(msg)
		assert.NotNil(t, msg)
		assert.Equal(t, expectedOrder[i], msg)
		c1.Acknowledge()
	}
}
