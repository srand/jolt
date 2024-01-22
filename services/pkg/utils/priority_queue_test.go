package utils

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestPriorityQueue(t *testing.T) {
	compareFunc := PriorityFunc[int](func(a, b any) int {
		if a.(int) < b.(int) {
			return 1
		} else if a.(int) > b.(int) {
			return -1
		}
		return 0
	})

	equalityFunc := EqualityFunc[int](func(a, b any) bool {
		return a.(int) == b.(int)
	})

	// Create a priority queue.
	pq := NewPriorityQueue[int](compareFunc, equalityFunc)

	// Push items to the priority queue
	pq.Push(3)
	pq.Push(1)
	pq.Push(2)

	// Verify pop order
	assert.Equal(t, 3, pq.Pop())
	assert.Equal(t, 2, pq.Pop())
	assert.Equal(t, 1, pq.Pop())

	// Remove an item from the priority queue
	pq.Push(1)
	pq.Push(4)
	pq.Push(5)
	pq.Remove(4)

	// Verify pop order after removal
	assert.Equal(t, 5, pq.Pop())
	assert.Equal(t, 1, pq.Pop())
}
