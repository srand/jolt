package cache

import (
	"io"
	"time"

	"github.com/srand/jolt/scheduler/pkg/utils"
)

type Cache interface {
	HasFile(path string) CacheItem
	ReadFile(path string) (io.ReadCloser, error)
	WriteFile(path string) (io.WriteCloser, error)

	HasObject(utils.Digest) CacheItem
	ReadObject(utils.Digest) (io.ReadCloser, error)
	WriteObject(utils.Digest) (io.WriteCloser, error)

	Statistics() CacheStats
}

type CacheConfig interface {
	MaxSize() int64
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
