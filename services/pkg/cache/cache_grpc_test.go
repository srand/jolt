package cache

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/hex"
	"io"
	"sort"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/fstree"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc"
)

// Cache that keeps track of readers that have not been closed.
type trackingCache struct {
	Cache
	open   atomic.Int64
	reads  atomic.Int64
	active atomic.Int64
	peak   atomic.Int64
	delay  time.Duration
}

type trackedReader struct {
	io.ReadCloser
	cache *trackingCache
	once  sync.Once
}

func (r *trackedReader) Close() error {
	r.once.Do(func() { r.cache.open.Add(-1) })
	return r.ReadCloser.Close()
}

func (c *trackingCache) ReadObject(d utils.Digest) (io.ReadCloser, error) {
	// Record how many lookups are in progress at once. The delay keeps
	// concurrent lookups overlapping so that the peak is observable.
	active := c.active.Add(1)
	defer c.active.Add(-1)
	for {
		peak := c.peak.Load()
		if active <= peak || c.peak.CompareAndSwap(peak, active) {
			break
		}
	}
	time.Sleep(c.delay)

	reader, err := c.Cache.ReadObject(d)
	if err != nil {
		return nil, err
	}
	c.open.Add(1)
	c.reads.Add(1)
	return &trackedReader{ReadCloser: reader, cache: c}, nil
}

// HasTree stream that records the responses sent to the client.
type hasTreeStream struct {
	grpc.ServerStream
	ctx       context.Context
	mu        sync.Mutex
	responses []*HasTreeResponse
}

func (s *hasTreeStream) Context() context.Context {
	return s.ctx
}

func (s *hasTreeStream) Send(r *HasTreeResponse) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.responses = append(s.responses, r)
	return nil
}

func (s *hasTreeStream) missing() (trees, objects []string) {
	for _, r := range s.responses {
		trees = append(trees, r.MissingTrees...)
		objects = append(objects, r.MissingObjects...)
	}
	sort.Strings(trees)
	sort.Strings(objects)
	return
}

type treeEntry struct {
	name   string
	digest string
	status uint32
}

func encodeTree(entries ...treeEntry) []byte {
	var buf bytes.Buffer
	binary.Write(&buf, binary.LittleEndian, uint16(fstree.TreeMagic))
	binary.Write(&buf, binary.LittleEndian, uint16(fstree.TreeVersion))
	for _, e := range entries {
		binary.Write(&buf, binary.LittleEndian, uint64(len(e.name)))
		buf.WriteString(e.name)
		binary.Write(&buf, binary.LittleEndian, uint64(len(e.digest)))
		buf.WriteString(e.digest)
		binary.Write(&buf, binary.LittleEndian, e.status)
		if e.status&fstree.InodeType_Symlink != 0 {
			binary.Write(&buf, binary.LittleEndian, uint64(len(e.name)))
			buf.WriteString(e.name)
		}
	}
	return buf.Bytes()
}

func blake3Digest(data []byte) string {
	h := utils.NewBlake3()
	h.Write(data)
	return "blake3:" + hex.EncodeToString(h.Sum(nil))
}

func newTestCache(t *testing.T) *trackingCache {
	config := &MockCacheConfig{}
	config.On("MaxSize").Return(1 << 30)
	config.On("ExpirationTime").Return(time.Duration(0))

	lru, err := NewLRUCache(afero.NewMemMapFs(), config)
	assert.NoError(t, err)
	return &trackingCache{Cache: lru}
}

// Store data in the cache and return its digest.
func put(t *testing.T, c Cache, data []byte) string {
	digest := blake3Digest(data)
	d, err := utils.ParseDigest(digest)
	assert.NoError(t, err)

	writer, err := c.WriteObject(d)
	assert.NoError(t, err)
	_, err = writer.Write(data)
	assert.NoError(t, err)
	assert.NoError(t, writer.Close())
	return digest
}

func hasTree(t *testing.T, c Cache, ctx context.Context, digests ...string) (*hasTreeStream, error) {
	stream := &hasTreeStream{ctx: ctx}
	err := NewCacheService(c).HasTree(&HasTreeRequest{Digest: digests}, stream)
	return stream, err
}

func TestHasTreeReportsMissing(t *testing.T) {
	c := newTestCache(t)

	present := put(t, c, []byte("present"))
	missingFile := blake3Digest([]byte("missing"))
	missingTree := blake3Digest([]byte("missing tree"))
	sub := put(t, c, encodeTree(
		treeEntry{"present.txt", present, fstree.InodeType_Regular},
		treeEntry{"missing.txt", missingFile, fstree.InodeType_Regular},
	))
	root := put(t, c, encodeTree(
		treeEntry{"sub", sub, fstree.InodeType_Directory},
		treeEntry{"gone", missingTree, fstree.InodeType_Directory},
		treeEntry{"link", "", fstree.InodeType_Symlink},
	))

	stream, err := hasTree(t, c, context.Background(), root)
	assert.NoError(t, err)

	trees, objects := stream.missing()
	assert.Equal(t, []string{missingTree}, trees)
	assert.Equal(t, []string{missingFile}, objects)
}

func TestHasTreeClosesReaders(t *testing.T) {
	c := newTestCache(t)

	file := put(t, c, []byte("file"))
	sub := put(t, c, encodeTree(treeEntry{"file.txt", file, fstree.InodeType_Regular}))
	root := put(t, c, encodeTree(treeEntry{"sub", sub, fstree.InodeType_Directory}))

	_, err := hasTree(t, c, context.Background(), root)
	assert.NoError(t, err)
	assert.Equal(t, int64(0), c.open.Load(), "tree readers left open")
}

func TestHasTreeStopsWhenCanceled(t *testing.T) {
	c := newTestCache(t)

	file := put(t, c, []byte("file"))
	sub := put(t, c, encodeTree(treeEntry{"file.txt", file, fstree.InodeType_Regular}))
	root := put(t, c, encodeTree(treeEntry{"sub", sub, fstree.InodeType_Directory}))

	// The client has gone away, there is no one to walk the tree for.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := hasTree(t, c, ctx, root)
	assert.Error(t, err)
	assert.Equal(t, int64(0), c.reads.Load(), "trees read after cancellation")
}

func TestHasTreeLimitsConcurrency(t *testing.T) {
	limit := hasTreeConcurrency
	hasTreeConcurrency = 4
	defer func() { hasTreeConcurrency = limit }()

	c := newTestCache(t)
	c.delay = time.Millisecond

	// A wide tree, where every subtree can be checked at once.
	file := put(t, c, []byte("file"))
	var subs []treeEntry
	for i := 0; i < 100; i++ {
		sub := put(t, c, encodeTree(
			treeEntry{"file.txt", file, fstree.InodeType_Regular},
			treeEntry{"unique", put(t, c, []byte{byte(i)}), fstree.InodeType_Regular},
		))
		subs = append(subs, treeEntry{string(rune('a' + i)), sub, fstree.InodeType_Directory})
	}
	root := put(t, c, encodeTree(subs...))

	_, err := hasTree(t, c, context.Background(), root)
	assert.NoError(t, err)

	// Subtrees run inline in the handler when no slot is free.
	assert.LessOrEqual(t, c.peak.Load(), int64(hasTreeConcurrency+1))
}

func TestHasTreeDeeperThanConcurrencyLimit(t *testing.T) {
	limit := hasTreeConcurrency
	hasTreeConcurrency = 2
	defer func() { hasTreeConcurrency = limit }()

	c := newTestCache(t)

	// Every level waits on the next, so a walk that blocks for a free slot
	// while holding one would deadlock here.
	missing := blake3Digest([]byte("missing"))
	tree := put(t, c, encodeTree(treeEntry{"missing.txt", missing, fstree.InodeType_Regular}))
	for i := 0; i < 20; i++ {
		tree = put(t, c, encodeTree(treeEntry{"sub", tree, fstree.InodeType_Directory}))
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	stream, err := hasTree(t, c, ctx, tree)
	assert.NoError(t, err)
	_, objects := stream.missing()
	assert.Equal(t, []string{missing}, objects)
}
