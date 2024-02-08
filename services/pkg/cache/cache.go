package cache

import (
	"io"
	"time"

	"github.com/srand/jolt/scheduler/pkg/utils"
)

// WriteCloseDiscarder is a combination of io.WriteCloser and a Discard method.
type WriteCloseDiscarder interface {
	io.WriteCloser

	// Discard the writer and the underlying resource.
	// This method should be called instead of Close() if an error occurs during writing.
	Discard() error
}

// Cache interface
type Cache interface {
	// Returns true if the cache contains the file at the given path.
	HasFile(path string) CacheItem

	// Returns a reader for the file at the given path.
	ReadFile(path string) (io.ReadCloser, error)

	// Returns a writer for the file at the given path.
	// If the file already exists, it will be overwritten on close.
	// If the file does not exist, it will be created on close.
	// Call Discard() instead of Close() if an error occurs during writing.
	WriteFile(path string) (WriteCloseDiscarder, error)

	// Returns true if the cache contains the object with the given digest.
	HasObject(utils.Digest) CacheItem

	// Returns a reader for the object with the given digest.
	ReadObject(utils.Digest) (io.ReadCloser, error)

	// Returns a writer for the object with the given digest.
	// If the object already exists, it will be overwritten on close.
	// If the object does not exist, it will be created on close.
	// Call Discard() instead of Close() if an error occurs during writing.
	WriteObject(utils.Digest) (WriteCloseDiscarder, error)

	// Returns statistics about the cache.
	Statistics() CacheStats
}

// Cache configuration
type CacheConfig interface {

	// Maximum allowed size of the cache in bytes.
	// If the cache size exceeds this value, the least recently used items will be evicted.
	// The limit is a soft limit, the cache may exceed this value temporarily.
	MaxSize() int64

	// Minimum expiration time for cache items after they are last accessed.
	// Items cannot be evicted before this time has passed even if the cache is full.
	ExpirationTime() time.Duration
}

type CacheItem interface {
	Size() int64
}

// Cache statistics
type CacheStats struct {
	// Total number of artifacts in the cache (files + objects)
	Artifacts int64

	// Total number of cache hits
	Hits int64

	// Total number of cache misses
	Misses int64

	// Total number of evicted artifacts
	Evictions int64

	// Total size of all artifacts in the cache in bytes
	Size int64
}
