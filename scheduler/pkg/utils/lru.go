package utils

import (
	"container/list"
	"sync"
)

// An item in the LRU cache.
type LRUItem interface {
	Path() string
	Size() int64
}

// A file in the LRU cache.
type LRUFile struct {
	// The path of the file.
	path string

	// The size of the file in bytes.
	size int64
}

// Create a new LRUFile.
func NewLRUFile(path string, size int64) *LRUFile {
	return &LRUFile{
		path: path,
		size: size,
	}
}

// Get the path of the file.
func (f *LRUFile) Path() string {
	return f.path
}

// Get the size of the file in bytes.
func (f *LRUFile) Size() int64 {
	return f.size
}

// EvictFunc is a function that is called when a file is evicted from the cache.
type EvictFunc[E LRUItem] func(item E)

// LRU is an LRU cache of files.
type LRU[E LRUItem] struct {
	mu sync.Mutex // For thread safety

	// The maximum size of the cache in bytes.
	maxSize int64

	// Current size of the cache.
	currentSize int64

	// Doubly-linked list of CacheItems.
	cacheList *list.List

	// Map to access any CacheItem in constant time.
	cacheMap map[string]*list.Element

	// Function to call when an item is evicted.
	onEvict EvictFunc[E]
}

// Creates a new LRU cache.
func NewLRU[E LRUItem](maxSize int64, onEvict EvictFunc[E]) *LRU[E] {
	return &LRU[E]{
		maxSize:   maxSize,
		cacheList: list.New(),
		cacheMap:  make(map[string]*list.Element),
		onEvict:   onEvict,
	}
}

// Add a new item to the cache.
func (lru *LRU[E]) Add(item E) {
	lru.mu.Lock()
	defer lru.mu.Unlock()

	// If CacheItem is already in cache, move it to front.
	if ee, ok := lru.cacheMap[item.Path()]; ok {
		lru.cacheList.MoveToFront(ee)
		ee.Value = item
		return
	}

	// Add new CacheItem to the cache.
	ele := lru.cacheList.PushFront(item)
	lru.cacheMap[item.Path()] = ele

	// Update the current size of the cache.
	lru.currentSize += item.Size()

	// If the cache is full, remove the least recently used CacheItem.
	for lru.currentSize > lru.maxSize {
		lru.removeOldest()
	}
}

// Get an item from the cache.
func (lru *LRU[E]) Get(path string) (item E, ok bool) {
	lru.mu.Lock()
	defer lru.mu.Unlock()

	if ele, hit := lru.cacheMap[path]; hit {
		lru.cacheList.MoveToFront(ele)
		return ele.Value.(E), true
	}
	return
}

// Remove the oldest item from the cache.
func (lru *LRU[E]) removeOldest() {
	ele := lru.cacheList.Back()
	if ele != nil {
		lru.removeElement(ele)

		// Call the eviction function if it's set.
		if lru.onEvict != nil {
			lru.onEvict(ele.Value.(E))
		}
	}
}

// Remove an item from the cache.
func (lru *LRU[E]) removeElement(e *list.Element) {
	lru.cacheList.Remove(e)
	kv := e.Value.(E)
	delete(lru.cacheMap, kv.Path())
	lru.currentSize -= kv.Size()
}

func (lru *LRU[E]) Remove(path string) {
	lru.mu.Lock()
	defer lru.mu.Unlock()

	if ele, hit := lru.cacheMap[path]; hit {
		lru.removeElement(ele)
	}
}
