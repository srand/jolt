package utils

import (
	"sync"
	"testing"
)

func TestWorkerPool(t *testing.T) {
	numResults := 10000

	pool := NewWorkerPool()
	pool.Start()

	var mu sync.Mutex
	results := make([]int, 0)

	for i := 0; i < numResults; i++ {
		n := i
		pool.SubmitOrRun(func() {
			mu.Lock()
			results = append(results, n)
			mu.Unlock()
		})
	}

	pool.Wait()

	if len(results) != numResults {
		t.Errorf("Expected %d results, got %d", numResults, len(results))
	}

	resultSet := make(map[int]struct{})
	for _, r := range results {
		resultSet[r] = struct{}{}
	}

	for i := 0; i < numResults; i++ {
		if _, ok := resultSet[i]; !ok {
			t.Errorf("Missing result: %d", i)
		}
	}
}
