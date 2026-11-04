package cache

import (
	"sync"
	"testing"
	"time"

	"github.com/spf13/afero"
	"github.com/stretchr/testify/assert"
)

// renameHookFs runs a hook after each rename, to interleave other
// operations with an upload that has just moved its file into place.
type renameHookFs struct {
	afero.Fs
	mu   sync.Mutex
	hook func(newname string)
}

func (fs *renameHookFs) Rename(oldname, newname string) error {
	if err := fs.Fs.Rename(oldname, newname); err != nil {
		return err
	}
	fs.mu.Lock()
	hook := fs.hook
	fs.hook = nil
	fs.mu.Unlock()
	if hook != nil {
		hook(newname)
	}
	return nil
}

func writeCacheFile(t *testing.T, c *lruCache, path string, data []byte) {
	writer, err := c.WriteFile(path)
	assert.NoError(t, err)
	_, err = writer.Write(data)
	assert.NoError(t, err)
	assert.NoError(t, writer.Close())
}

// An upload of a file that is already in the cache renames the new file
// over the old one. Eviction of the old entry must not remove the new
// file before the entry is updated: the upload then failed, or the cache
// kept an entry for a file that is gone ("inconsistent cache: file not
// found on disk").
func TestLRUEvictionDuringReupload(t *testing.T) {
	config := &MockCacheConfig{}
	config.On("MaxSize").Return(15)
	config.On("ExpirationTime").Return(time.Duration(0))

	fs := &renameHookFs{Fs: afero.NewMemMapFs()}
	c, err := NewLRUCache(fs, config)
	assert.NoError(t, err)

	writeCacheFile(t, c, "task/a.tar.zst", []byte("0123456789"))

	// Upload a again. Right after its file is renamed into place, another
	// upload fills the cache and evicts the least recently used entry.
	done := make(chan struct{})
	fs.hook = func(string) {
		go func() {
			defer close(done)
			writeCacheFile(t, c, "task/b.tar.zst", []byte("0123456789"))
		}()
		select {
		case <-done:
		case <-time.After(200 * time.Millisecond):
		}
	}
	writeCacheFile(t, c, "task/a.tar.zst", []byte("0123456789"))
	<-done

	for _, path := range []string{"files/task/a.tar.zst", "files/task/b.tar.zst"} {
		if _, ok := c.lru.Get(path); ok {
			_, err := fs.Stat(path)
			assert.NoError(t, err, "cache has an entry for %s but no file", path)
		}
	}
}
