package cache

import (
	"testing"
	"time"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/suite"
)

type MockCacheConfig struct {
	mock.Mock
}

func (m *MockCacheConfig) MaxSize() int64 {
	args := m.Called()
	return int64(args.Int(0))
}

func (m *MockCacheConfig) ExpirationTime() time.Duration {
	args := m.Called()
	return args.Get(0).(time.Duration)
}

type LRUCacheTestSuite struct {
	suite.Suite
	config MockCacheConfig
	fs     utils.Fs
}

func (suite *LRUCacheTestSuite) SetupTest() {
	log.SetLevel(log.TraceLevel)

	suite.fs = afero.NewMemMapFs()

	suite.config.ExpectedCalls = []*mock.Call{}
	suite.config.On("MaxSize").Return(2)
	suite.config.On("ExpirationTime").Return(time.Duration(0))
}

func (s *LRUCacheTestSuite) newCache() Cache {
	cache, err := NewLRUCache(s.fs, &s.config)
	assert.NoError(s.T(), err)
	return cache
}

func (s *LRUCacheTestSuite) write(cache Cache, d utils.Digest, data []byte) {
	writer, err := cache.WriteObject(d)
	assert.NoError(s.T(), err)

	n, err := writer.Write(data)
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), len(data), n)

	err = writer.Close()
	assert.NoError(s.T(), err)
}

func (s *LRUCacheTestSuite) read(cache Cache, d utils.Digest, data []byte) (int, error) {
	reader, err := cache.ReadObject(d)
	if err != nil {
		return 0, err
	}
	defer reader.Close()
	return reader.Read(data)
}

func (s *LRUCacheTestSuite) TestCRUD() {
	cache := s.newCache()

	d1 := utils.NewDigest(utils.Sha1Algorithm, "add7c3dfeb73b946f502617c8bedce90a643449c")
	d2 := utils.NewDigest(utils.Sha1Algorithm, "d94c1a9b0332374724faf31b0e0d6d9136d3e9c6")

	// Lookup item, should not exist
	assert.Nil(s.T(), cache.HasObject(d1))
	assert.Nil(s.T(), cache.HasObject(d2))

	// Create item
	s.write(cache, d1, []byte{1})
	s.write(cache, d2, []byte{2})

	assert.NotNil(s.T(), cache.HasObject(d1))
	assert.NotNil(s.T(), cache.HasObject(d2))

	// Read back item
	data := make([]byte, 32)
	n, err := s.read(cache, d1, data)
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), 1, n)
	assert.Equal(s.T(), byte(1), data[0])

	n, err = s.read(cache, d2, data)
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), 1, n)
	assert.Equal(s.T(), byte(2), data[0])
}

func (s *LRUCacheTestSuite) TestEvict() {
	cache := s.newCache()

	d1 := utils.NewDigest(utils.Sha1Algorithm, "add7c3dfeb73b946f502617c8bedce90a643449c")
	d2 := utils.NewDigest(utils.Sha1Algorithm, "d94c1a9b0332374724faf31b0e0d6d9136d3e9c6")
	d3 := utils.NewDigest(utils.Sha1Algorithm, "61d7f800bc3671812a28d6380b070b2b0ff7fda3")

	// Create items
	s.write(cache, d1, []byte{1})
	s.write(cache, d2, []byte{2})
	s.write(cache, d3, []byte{3})

	assert.Nil(s.T(), cache.HasObject(d1))
	assert.NotNil(s.T(), cache.HasObject(d2))
	assert.NotNil(s.T(), cache.HasObject(d3))
}

func (s *LRUCacheTestSuite) TestConditionalEvict() {
	// Reset expectations and allow eviction 1 hour after use
	s.config.ExpectedCalls = []*mock.Call{}
	s.config.On("MaxSize").Return(2)
	s.config.On("ExpirationTime").Return(time.Hour)

	cache := s.newCache()

	d1 := utils.NewDigest(utils.Sha1Algorithm, "add7c3dfeb73b946f502617c8bedce90a643449c")
	d2 := utils.NewDigest(utils.Sha1Algorithm, "d94c1a9b0332374724faf31b0e0d6d9136d3e9c6")
	d3 := utils.NewDigest(utils.Sha1Algorithm, "61d7f800bc3671812a28d6380b070b2b0ff7fda3")

	// Create items
	s.write(cache, d1, []byte{1})
	s.write(cache, d2, []byte{2})
	s.write(cache, d3, []byte{3})

	// No item should have been evicted (an hour hasn't passed)
	assert.NotNil(s.T(), cache.HasObject(d1))
	assert.NotNil(s.T(), cache.HasObject(d2))
	assert.NotNil(s.T(), cache.HasObject(d3))
}

func (s *LRUCacheTestSuite) TestEvictOrder() {
	cache := s.newCache()

	d1 := utils.NewDigest(utils.Sha1Algorithm, "add7c3dfeb73b946f502617c8bedce90a643449c")
	d2 := utils.NewDigest(utils.Sha1Algorithm, "d94c1a9b0332374724faf31b0e0d6d9136d3e9c6")
	d3 := utils.NewDigest(utils.Sha1Algorithm, "61d7f800bc3671812a28d6380b070b2b0ff7fda3")

	// Create items
	s.write(cache, d1, []byte{1})
	s.write(cache, d2, []byte{2})

	// Access first item, making it most recently used
	cache.HasObject(d1)

	// Create a third item.
	s.write(cache, d3, []byte{3})

	// d2 was LRU and should have been evicted
	assert.NotNil(s.T(), cache.HasObject(d1))
	assert.Nil(s.T(), cache.HasObject(d2))
	assert.NotNil(s.T(), cache.HasObject(d3))
}

func TestLRUCacheTestSuite(t *testing.T) {
	suite.Run(t, new(LRUCacheTestSuite))
}
