package cache

import (
	"bytes"
	"context"
	"crypto/sha1"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"sort"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/fstree"
	"github.com/srand/jolt/scheduler/pkg/log"
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

	// Objects to treat as evicted, by digest string
	evicted sync.Map
}

func (c *trackingCache) evict(digest string) {
	d, _ := utils.ParseDigest(digest)
	c.evicted.Store(d.String(), true)
}

func (c *trackingCache) isEvicted(d utils.Digest) bool {
	_, found := c.evicted.Load(d.String())
	return found
}

func (c *trackingCache) HasObject(d utils.Digest) CacheItem {
	if c.isEvicted(d) {
		return nil
	}
	return c.Cache.HasObject(d)
}

func (c *trackingCache) HasObjects(digests []utils.Digest) []CacheItem {
	items := c.Cache.HasObjects(digests)
	for i, d := range digests {
		if c.isEvicted(d) {
			items[i] = nil
		}
	}
	return items
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

	if c.isEvicted(d) {
		return nil, utils.ErrNotFound
	}

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

func newTestCache(t testing.TB) *trackingCache {
	config := &MockCacheConfig{}
	config.On("MaxSize").Return(1 << 30)
	config.On("ExpirationTime").Return(time.Duration(0))

	lru, err := NewLRUCache(afero.NewMemMapFs(), config)
	assert.NoError(t, err)
	return &trackingCache{Cache: lru}
}

// Store data in the cache and return its digest.
func put(t testing.TB, c Cache, data []byte) string {
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

func hasTree(t testing.TB, c Cache, ctx context.Context, digests ...string) (*hasTreeStream, error) {
	return hasTreeWith(NewCacheService(c, 64<<20), ctx, digests...)
}

// Calls HasTree on a given service, which keeps what it learns between calls.
func hasTreeWith(svc CacheServiceServer, ctx context.Context, digests ...string) (*hasTreeStream, error) {
	stream := &hasTreeStream{ctx: ctx}
	err := svc.HasTree(&HasTreeRequest{Digest: digests}, stream)
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

func TestHasTreeVisitsDuplicatesOnce(t *testing.T) {
	c := newTestCache(t)

	// The same subtree appears twice, as identical directories do, and
	// the same missing file appears in both it and the root.
	missing := blake3Digest([]byte("missing"))
	sub := put(t, c, encodeTree(treeEntry{"missing.txt", missing, fstree.InodeType_Regular}))
	root := put(t, c, encodeTree(
		treeEntry{"a", sub, fstree.InodeType_Directory},
		treeEntry{"b", sub, fstree.InodeType_Directory},
		treeEntry{"missing.txt", missing, fstree.InodeType_Regular},
	))

	stream, err := hasTree(t, c, context.Background(), root, root)
	assert.NoError(t, err)

	_, objects := stream.missing()
	assert.Equal(t, []string{missing}, objects, "missing object reported more than once")
	assert.Equal(t, int64(2), c.reads.Load(), "trees read more than once")
}

// Measures HasTree on a workspace that is already complete in a cache
// stored on disk, which is what every push of an unchanged workspace costs.
func BenchmarkHasTreeComplete(b *testing.B) {
	log.SetLevel(log.WarningLevel)

	config := &MockCacheConfig{}
	config.On("MaxSize").Return(1 << 30)
	config.On("ExpirationTime").Return(time.Duration(0))

	lru, err := NewLRUCache(afero.NewBasePathFs(afero.NewOsFs(), b.TempDir()), config)
	assert.NoError(b, err)

	var dirs []treeEntry
	for d := 0; d < 200; d++ {
		var files []treeEntry
		for f := 0; f < 50; f++ {
			digest := put(b, lru, []byte(fmt.Sprintf("file %d %d", d, f)))
			files = append(files, treeEntry{fmt.Sprintf("file%d.txt", f), digest, fstree.InodeType_Regular})
		}
		dirs = append(dirs, treeEntry{fmt.Sprintf("dir%d", d), put(b, lru, encodeTree(files...)), fstree.InodeType_Directory})
	}
	root := put(b, lru, encodeTree(dirs...))

	// The service runs for as long as the cache, so it is shared by all
	// calls, as it is by all pushes.
	svc := NewCacheService(lru, 64<<20)

	b.ReportAllocs()
	b.ResetTimer()
	cpuStart, cpuOk := processCPUTime()
	for i := 0; i < b.N; i++ {
		stream, err := hasTreeWith(svc, context.Background(), root)
		if err != nil || len(stream.responses) != 0 {
			b.Fatal("tree not complete", err)
		}
	}

	// HasTree runs its checks in parallel, so the time it takes says little
	// about the CPU time it costs a busy service.
	if cpuEnd, ok := processCPUTime(); ok && cpuOk {
		b.ReportMetric(float64(cpuEnd-cpuStart)/float64(b.N), "cpu-ns/op")
	}
}

func TestHasTreeKeepsParsedTrees(t *testing.T) {
	c := newTestCache(t)

	file := put(t, c, []byte("file"))
	sub := put(t, c, encodeTree(treeEntry{"file.txt", file, fstree.InodeType_Regular}))
	root := put(t, c, encodeTree(treeEntry{"sub", sub, fstree.InodeType_Directory}))

	svc := NewCacheService(c, 64<<20)
	_, err := hasTreeWith(svc, context.Background(), root)
	assert.NoError(t, err)
	reads := c.reads.Load()

	// Tree objects never change, so a service reads each only once.
	stream, err := hasTreeWith(svc, context.Background(), root)
	assert.NoError(t, err)
	assert.Empty(t, stream.responses)
	assert.Equal(t, reads, c.reads.Load(), "tree objects read again")
}

func TestHasTreeReportsEvictedParsedTree(t *testing.T) {
	c := newTestCache(t)

	file := put(t, c, []byte("file"))
	sub := put(t, c, encodeTree(treeEntry{"file.txt", file, fstree.InodeType_Regular}))
	root := put(t, c, encodeTree(treeEntry{"sub", sub, fstree.InodeType_Directory}))

	svc := NewCacheService(c, 64<<20)
	_, err := hasTreeWith(svc, context.Background(), root)
	assert.NoError(t, err)

	// A tree whose object was evicted must be uploaded again, even though
	// the service still knows its content, or it could not be pulled.
	c.evict(sub)
	stream, err := hasTreeWith(svc, context.Background(), root)
	assert.NoError(t, err)
	trees, objects := stream.missing()
	assert.Equal(t, []string{sub}, trees)
	assert.Empty(t, objects)

	// Likewise an evicted object of a tree the service knows.
	c.evicted.Delete(sub)
	c.evict(file)
	stream, err = hasTreeWith(svc, context.Background(), root)
	assert.NoError(t, err)
	trees, objects = stream.missing()
	assert.Empty(t, trees)
	assert.Equal(t, []string{file}, objects)
}

func TestHasTreeMetrics(t *testing.T) {
	c := newTestCache(t)

	file := put(t, c, []byte("file"))
	sub := put(t, c, encodeTree(treeEntry{"file.txt", file, fstree.InodeType_Regular}))
	root := put(t, c, encodeTree(treeEntry{"sub", sub, fstree.InodeType_Directory}))

	svc := NewCacheService(c, 64<<20)
	for range 2 {
		_, err := hasTreeWith(svc, context.Background(), root)
		assert.NoError(t, err)
	}

	response := httptest.NewRecorder()
	NewHttpHandler(c, svc).ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	assert.Equal(t, http.StatusOK, response.Code)
	body := response.Body.String()

	for _, metric := range []struct {
		name, kind string
		value      int64
	}{
		{"jolt_cache_hastree_requests_total", "counter", 2},
		{"jolt_cache_hastree_trees_total", "counter", 4},
		{"jolt_cache_hastree_objects_total", "counter", 2},
		// Both trees are read and parsed by the first request only.
		{"jolt_cache_tree_cache_misses_total", "counter", 2},
		{"jolt_cache_tree_cache_hits_total", "counter", 2},
		{"jolt_cache_tree_cache_evictions_total", "counter", 0},
		{"jolt_cache_tree_cache_trees", "gauge", 2},
		{"jolt_cache_tree_cache_size_bytes", "gauge", 4 * parsedTreeDigestSize},
	} {
		assert.Contains(t, body, fmt.Sprintf("# TYPE %s %s\n# HELP %s ", metric.name, metric.kind, metric.name))
		assert.Contains(t, body, fmt.Sprintf("\n%s %d\n", metric.name, metric.value))
	}
	assert.Contains(t, body, "# TYPE jolt_cache_hastree_seconds_total counter\n")
	assert.Regexp(t, `\njolt_cache_hastree_seconds_total [0-9.e-]+\n`, body)

	// Without a service, the handler reports the cache only.
	response = httptest.NewRecorder()
	NewHttpHandler(c, nil).ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	assert.NotContains(t, response.Body.String(), "hastree")
	assert.Contains(t, response.Body.String(), "jolt_cache_artifacts")
}

// Stores data in the cache as a sha1 object and returns its digest as bare
// hex, as fstree releases before 26 named objects.
func putSha1(t testing.TB, c Cache, data []byte) string {
	sum := sha1.Sum(data)
	hex := hex.EncodeToString(sum[:])

	writer, err := c.WriteObject(utils.NewDigest(utils.Sha1Algorithm, hex))
	assert.NoError(t, err)
	_, err = writer.Write(data)
	assert.NoError(t, err)
	assert.NoError(t, writer.Close())
	return hex
}

func TestHasTreeReportsDigestsAsTheClientWroteThem(t *testing.T) {
	c := newTestCache(t)

	// A client that names objects by bare hex, as older fstree releases do,
	// looks reported objects up by name and must get them back in that form.
	sum := sha1.Sum([]byte("missing"))
	missingFile := hex.EncodeToString(sum[:])
	sum = sha1.Sum([]byte("missing tree"))
	missingTree := hex.EncodeToString(sum[:])

	present := putSha1(t, c, []byte("present"))
	root := putSha1(t, c, encodeTree(
		treeEntry{"present.txt", present, fstree.InodeType_Regular},
		treeEntry{"missing.txt", missingFile, fstree.InodeType_Regular},
		treeEntry{"gone", missingTree, fstree.InodeType_Directory},
	))

	svc := NewCacheService(c, 64<<20)
	for range 2 {
		// Once read from the object and once from the parsed tree kept
		stream, err := hasTreeWith(svc, context.Background(), root)
		assert.NoError(t, err)
		trees, objects := stream.missing()
		assert.Equal(t, []string{missingTree}, trees)
		assert.Equal(t, []string{missingFile}, objects)
	}

	// A missing tree named in the request is reported as it was named.
	sum = sha1.Sum([]byte("absent root"))
	absent := hex.EncodeToString(sum[:])
	for _, name := range []string{absent, "sha1:" + absent} {
		stream, err := hasTreeWith(svc, context.Background(), name)
		assert.NoError(t, err)
		trees, _ := stream.missing()
		assert.Equal(t, []string{name}, trees)
	}
}
