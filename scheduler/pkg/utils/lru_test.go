package utils

import (
	"testing"

	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/suite"
)

type TestItem struct {
	path string
	size int64
}

func (item TestItem) Path() string {
	return item.path
}

func (item TestItem) Size() int64 {
	return item.size
}

type EvictFuncMock struct {
	mock.Mock
}

func (m *EvictFuncMock) Evict(item TestItem) {
	m.Called(item)
}

type LRUTestSuite struct {
	suite.Suite
	lru  *LRU[TestItem]
	mock *EvictFuncMock
}

func (suite *LRUTestSuite) SetupTest() {
	suite.mock = new(EvictFuncMock)
	suite.lru = NewLRU(2, suite.mock.Evict)
}

func (suite *LRUTestSuite) TestEvict() {
	item1 := TestItem{path: "item1", size: 1}
	item2 := TestItem{path: "item2", size: 1}
	item3 := TestItem{path: "item3", size: 1}

	suite.lru.Add(item1)
	suite.lru.Add(item2)

	suite.mock.On("Evict", item1).Once()

	suite.lru.Add(item3)

	suite.mock.AssertExpectations(suite.T())
}

func (suite *LRUTestSuite) TestLRUProperty() {
	item1 := TestItem{path: "item1", size: 1}
	item2 := TestItem{path: "item2", size: 1}
	item3 := TestItem{path: "item3", size: 1}

	suite.lru.Add(item1)
	suite.lru.Add(item2)

	// Access item1 to make it recently used.
	_, ok := suite.lru.Get("item1")
	suite.True(ok, "Expected to find item1 in cache")

	suite.mock.On("Evict", item2).Once()

	// Add item3 to the cache. This should evict item2 because item1 was recently used.
	suite.lru.Add(item3)

	suite.mock.AssertExpectations(suite.T())

	// Verify that item2 was evicted.
	_, ok = suite.lru.Get("item2")
	suite.False(ok, "Expected item2 to be evicted from cache")

	// Verify that item3 was added to the cache.
	_, ok = suite.lru.Get("item3")
	suite.True(ok, "Expected to find item3 in cache")
}

func TestLRUTestSuite(t *testing.T) {
	suite.Run(t, new(LRUTestSuite))
}
