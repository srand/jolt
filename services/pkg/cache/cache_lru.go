package cache

import (
	"io"
	"io/fs"
	"path"
	"path/filepath"
	"sync"
	"time"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type lruItem struct {
	access time.Time
	path   string
	size   int64
}

func (i *lruItem) Path() string {
	return i.path
}

func (i *lruItem) Size() int64 {
	return i.size
}

type lruFile struct {
	cache *lruCache
	file  utils.File
	path  string
}

func (f *lruFile) Read(data []byte) (int, error) {
	return f.file.Read(data)
}

func (f *lruFile) Write(data []byte) (int, error) {
	return f.file.Write(data)
}

func (f *lruFile) Close() error {
	err := f.file.Close()
	return f.cache.fileClosed(f, err)
}

func (f *lruFile) Discard() error {
	f.file.Close()
	return f.cache.fileDiscarded(f)
}

type lruCache struct {
	sync.Mutex

	config CacheConfig
	fs     utils.Fs
	lru    *utils.LRU[*lruItem]
	stats  CacheStats
}

func NewLRUCache(fs utils.Fs, config CacheConfig) (*lruCache, error) {
	log.Info("Maximum size:", utils.HumanByteSize(config.MaxSize()))

	cache := &lruCache{
		config: config,
		fs:     fs,
	}

	cache.lru = utils.NewLRU[*lruItem](config.MaxSize(), func(item *lruItem) bool {
		// Only allowed to evict items after not being used for a period of time
		if item.access.Add(config.ExpirationTime()).After(time.Now()) {
			return false
		}

		cache.stats.Evictions++

		log.Tracef("Evicting %s (%s)", item.path, utils.HumanByteSize(item.size))
		fs.Remove(item.path)
		return true
	})

	if err := cache.load(); err != nil {
		return nil, err
	}

	return cache, nil
}

func (c *lruCache) pathFromDigest(digest utils.Digest) string {
	hex := digest.Hex()
	return path.Join("objects", hex[:2], hex[2:6], hex[6:])
}

func (c *lruCache) hasFile(path string) CacheItem {
	c.Lock()
	defer c.Unlock()

	// Check if the file is in the cache
	item, found := c.lru.Get(path)
	if !found {
		c.stats.Misses++
		return nil
	}

	// Check if the file still exists on disk
	if _, err := c.fs.Stat(path); err != nil {
		log.Warn("inconsistent cache: file not found on disk:", path)
		c.lru.Remove(path)
		c.stats.Misses++
		return nil
	}

	item.access = time.Now()
	c.stats.Hits++
	return item
}

func (c *lruCache) readFile(path string) (io.ReadCloser, error) {
	c.Lock()
	defer c.Unlock()

	// Check if the file is in the cache
	item, ok := c.lru.Get(path)
	if !ok {
		c.stats.Misses++
		return nil, utils.ErrNotFound
	}

	file, err := c.fs.Open(path)
	if err != nil {
		log.Warn("inconsistent cache: file not found on disk:", path)
		c.lru.Remove(path)
		c.stats.Misses++
		return nil, err
	}

	item.access = time.Now()
	c.stats.Hits++
	return file, nil
}

func (c *lruCache) writeFile(path string) (WriteCloseDiscarder, error) {
	c.Lock()
	defer c.Unlock()

	dirpath := filepath.Dir(path)
	err := c.fs.MkdirAll(dirpath, 0777)
	if err != nil {
		return nil, err
	}

	file, err := afero.TempFile(c.fs, dirpath, "")
	if err != nil {
		return nil, err
	}

	return &lruFile{cache: c, file: file, path: path}, nil
}

func (c *lruCache) HasFile(path string) CacheItem {
	return c.hasFile(filepath.Join("files", path))
}

func (c *lruCache) ReadFile(path string) (io.ReadCloser, error) {
	return c.readFile(filepath.Join("files", path))
}

func (c *lruCache) WriteFile(path string) (WriteCloseDiscarder, error) {
	return c.writeFile(filepath.Join("files", path))
}

func (c *lruCache) HasObject(digest utils.Digest) CacheItem {
	path := c.pathFromDigest(digest)
	return c.HasFile(path)
}

func (c *lruCache) ReadObject(digest utils.Digest) (io.ReadCloser, error) {
	path := c.pathFromDigest(digest)
	return c.ReadFile(path)
}

func (c *lruCache) WriteObject(digest utils.Digest) (WriteCloseDiscarder, error) {
	path := c.pathFromDigest(digest)
	return c.WriteFile(path)
}

func (c *lruCache) Statistics() CacheStats {
	c.Lock()
	defer c.Unlock()

	c.stats.Artifacts = int64(c.lru.Count())
	c.stats.Size = c.lru.Size()
	return c.stats
}

func (c *lruCache) fileClosed(file *lruFile, err error) error {
	c.Lock()
	defer c.Unlock()

	if err != nil {
		c.fs.Remove(file.file.Name())
		return err
	}

	err = c.fs.Rename(file.file.Name(), file.path)
	if err != nil {
		c.fs.Remove(file.file.Name())
		return err
	}

	info, err := c.fs.Stat(file.path)
	if err != nil {
		c.fs.Remove(file.path)
		return err
	}

	c.lru.Add(&lruItem{
		access: time.Now(),
		path:   file.path,
		size:   info.Size(),
	})

	return nil
}

func (c *lruCache) fileDiscarded(file *lruFile) error {
	c.Lock()
	defer c.Unlock()
	return c.fs.Remove(file.file.Name())
}

func (c *lruCache) load() error {
	count := 0

	err := afero.Walk(c.fs, ".", func(path string, info fs.FileInfo, err error) error {
		if path == "." {
			return nil
		}

		if err != nil {
			return err
		}

		if info.IsDir() {
			return nil
		}

		c.lru.Add(&lruItem{
			access: info.ModTime(),
			path:   path,
			size:   info.Size(),
		})

		count++
		return nil
	})
	if err != nil {
		return err
	}

	log.Infof("Loaded %d items from storage into cache. Total size: %s", count, utils.HumanByteSize(c.lru.Size()))

	return nil
}
