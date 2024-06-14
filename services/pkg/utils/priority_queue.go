package utils

import "container/heap"

// Compares the priority of items in a priority queue.
type PriorityFunc[T any] func(a, b any) int

// Returns true if two items are identical.
type EqualityFunc[T any] func(a, b any) bool

// A priority queue.
type PriorityQueue[T any] struct {
	// The heap used to implement the priority queue.
	heap priorityHeap[T]

	// The function used to determine if two items are identical.
	equals EqualityFunc[T]
}

// Creates a new priority queue.
func NewPriorityQueue[T any](compare PriorityFunc[T], equals EqualityFunc[T]) *PriorityQueue[T] {
	return &PriorityQueue[T]{
		heap: priorityHeap[T]{
			items:   make([]T, 0),
			compare: compare,
		},
		equals: equals,
	}
}

// Pushes an item onto the priority queue.
func (pq *PriorityQueue[T]) Push(item T) {
	heap.Push(&pq.heap, item)
}

// Pops the highest priority item from the priority queue.
func (pq *PriorityQueue[T]) Pop() T {
	return heap.Pop(&pq.heap).(T)
}

// Returns the number of items in the priority queue.
func (pq *PriorityQueue[T]) Len() int {
	return pq.heap.Len()
}

// Removes an item from the priority queue.
func (pq *PriorityQueue[T]) Remove(item T) {
	for i, x := range pq.heap.items {
		if pq.equals(x, item) {
			heap.Remove(&pq.heap, i)
			return
		}
	}
}

// Returns true if an item is in the priority queue.
func (pq *PriorityQueue[T]) Contains(item T) bool {
	for _, x := range pq.heap.items {
		if pq.equals(x, item) {
			return true
		}
	}
	return false
}

// Returns the items in the priority queue as a list.
func (pq *PriorityQueue[T]) Items() []T {
	return pq.heap.Items()
}

// Reorders the priority queue.
func (pq *PriorityQueue[T]) Reorder() {
	heap.Init(&pq.heap)
}

type priorityHeap[T any] struct {
	// The items in the heap.
	items []T

	// The function used to compare items.
	compare PriorityFunc[T]
}

func (pq priorityHeap[T]) Len() int {
	return len(pq.items)
}

func (pq priorityHeap[T]) Less(i, j int) bool {
	return pq.compare(pq.items[i], pq.items[j]) < 0
}

func (pq priorityHeap[T]) Swap(i, j int) {
	pq.items[i], pq.items[j] = pq.items[j], pq.items[i]
}

func (pq *priorityHeap[T]) Push(x any) {
	pq.items = append(pq.items, x.(T))
}

func (pq *priorityHeap[T]) Pop() any {
	n := len(pq.items)
	x := pq.items[n-1]
	pq.items = pq.items[:n-1]
	return x
}

func (pq *priorityHeap[T]) Items() []T {
	return pq.items
}
