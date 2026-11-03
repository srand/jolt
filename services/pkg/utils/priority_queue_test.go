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

func TestPriorityQueueContainsAndLen(t *testing.T) {
	pq := NewPriorityQueue[int](
		func(a, b any) int { return a.(int) - b.(int) },
		func(a, b any) bool { return a.(int) == b.(int) },
	)
	assert.Equal(t, 0, pq.Len())
	assert.Empty(t, pq.Items())
	assert.False(t, pq.Contains(0))

	pq.Push(2)
	pq.Push(1)
	assert.Equal(t, 2, pq.Len())
	assert.True(t, pq.Contains(1))
	assert.False(t, pq.Contains(3))
	assert.ElementsMatch(t, []int{1, 2}, pq.Items())

	// Removing an item that isn't queued does nothing
	pq.Remove(3)
	assert.Equal(t, 2, pq.Len())

	// Equal items keep their place in the heap
	pq.Push(1)
	assert.Equal(t, 1, pq.Pop())
	assert.Equal(t, 1, pq.Pop())
	assert.Equal(t, 2, pq.Pop())
	assert.Equal(t, 0, pq.Len())
}

func TestPriorityQueueReorder(t *testing.T) {
	// Items whose priority changes are put in order by Reorder.
	priority := map[string]int{"a": 1, "b": 2, "c": 3}
	pq := NewPriorityQueue[string](
		func(a, b any) int { return priority[a.(string)] - priority[b.(string)] },
		func(a, b any) bool { return a.(string) == b.(string) },
	)
	pq.Push("a")
	pq.Push("b")
	pq.Push("c")

	priority["a"] = 4
	pq.Reorder()
	assert.Equal(t, "b", pq.Pop())
	assert.Equal(t, "c", pq.Pop())
	assert.Equal(t, "a", pq.Pop())
}
