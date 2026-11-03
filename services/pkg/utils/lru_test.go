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

func (m *EvictFuncMock) Evict(item TestItem) bool {
	args := m.Called(item)
	return args.Bool(0)
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

	suite.mock.On("Evict", item1).Return(true).Once()

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

	suite.mock.On("Evict", item2).Return(true).Once()

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

func (suite *LRUTestSuite) TestConditionalEvict() {
	item1 := TestItem{path: "item1", size: 1}
	item2 := TestItem{path: "item2", size: 1}
	item3 := TestItem{path: "item3", size: 1}
	item4 := TestItem{path: "item4", size: 1}
	item5 := TestItem{path: "item5", size: 1}

	suite.mock.On("Evict", item1).Return(false)
	suite.mock.On("Evict", item2).Return(false)
	suite.mock.On("Evict", item3).Return(false)
	suite.mock.On("Evict", item4).Return(true)
	suite.mock.On("Evict", item5).Return(false)

	suite.lru.Add(item1)
	suite.lru.Add(item2)
	suite.lru.Add(item3)
	suite.lru.Add(item4)
	suite.lru.Add(item5)

	_, ok := suite.lru.Get("item1")
	suite.True(ok, "Expected item1 to be evicted from cache")
	_, ok = suite.lru.Get("item2")
	suite.True(ok, "Expected item2 to be evicted from cache")
	_, ok = suite.lru.Get("item3")
	suite.True(ok, "Expected item3 to be evicted from cache")
	_, ok = suite.lru.Get("item4")
	suite.False(ok, "Expected item4 to be evicted from cache")
	_, ok = suite.lru.Get("item5")
	suite.True(ok, "Expected item5 to be evicted from cache")
}

func TestLRUTestSuite(t *testing.T) {
	suite.Run(t, new(LRUTestSuite))
}

func (suite *LRUTestSuite) TestUpdateAll() {
	item1 := TestItem{path: "item1", size: 1}
	item2 := TestItem{path: "item2", size: 1}
	suite.lru.Add(item1)
	suite.lru.Add(item2)

	var updated []string
	items, found := suite.lru.UpdateAll([]string{"item2", "missing", "item1"}, func(item TestItem) {
		updated = append(updated, item.path)
	})

	suite.Equal([]bool{true, false, true}, found)
	suite.Equal([]TestItem{item2, {}, item1}, items)
	suite.Equal([]string{"item2", "item1"}, updated)

	// Item1 was updated last and is now the most recently used, so item2 is
	// the one evicted to make room.
	item3 := TestItem{path: "item3", size: 1}
	suite.mock.On("Evict", item2).Return(true)
	suite.lru.Add(item3)
	suite.mock.AssertExpectations(suite.T())
}

func (suite *LRUTestSuite) TestFullCacheIsNotTrimmed() {
	// Items are only evicted when the size exceeds the maximum.
	suite.lru = NewLRU(3, suite.mock.Evict)
	suite.lru.Add(TestItem{path: "item1", size: 1})
	suite.lru.Add(TestItem{path: "item2", size: 2})

	suite.Equal(2, suite.lru.Count())
	suite.Equal(int64(3), suite.lru.Size())
	suite.mock.AssertNotCalled(suite.T(), "Evict", mock.Anything)
}

func (suite *LRUTestSuite) TestEvictUntilBelowMaximum() {
	// Several items are evicted if needed to make room for a large one.
	suite.lru = NewLRU(4, suite.mock.Evict)
	item1 := TestItem{path: "item1", size: 1}
	item2 := TestItem{path: "item2", size: 1}
	item3 := TestItem{path: "item3", size: 2}
	item4 := TestItem{path: "item4", size: 3}
	suite.lru.Add(item1)
	suite.lru.Add(item2)
	suite.lru.Add(item3)

	suite.mock.On("Evict", item1).Return(true).Once()
	suite.mock.On("Evict", item2).Return(true).Once()
	suite.mock.On("Evict", item3).Return(true).Once()
	suite.lru.Add(item4)
	suite.mock.AssertExpectations(suite.T())

	suite.Equal(1, suite.lru.Count())
	suite.Equal(int64(3), suite.lru.Size())
}

func (suite *LRUTestSuite) TestRemove() {
	suite.lru = NewLRU(10, suite.mock.Evict)
	suite.lru.Add(TestItem{path: "item1", size: 2})
	suite.lru.Add(TestItem{path: "item2", size: 3})

	suite.lru.Remove("item1")
	suite.lru.Remove("missing")
	suite.Equal(1, suite.lru.Count())
	suite.Equal(int64(3), suite.lru.Size())
	_, ok := suite.lru.Get("item1")
	suite.False(ok)
}

func (suite *LRUTestSuite) TestUpdate() {
	item1 := TestItem{path: "item1", size: 1}
	suite.lru.Add(item1)

	item, ok := suite.lru.Update("item1", nil)
	suite.True(ok)
	suite.Equal(item1, item)

	var updated []TestItem
	item, ok = suite.lru.Update("item1", func(item TestItem) { updated = append(updated, item) })
	suite.True(ok)
	suite.Equal(item1, item)
	suite.Equal([]TestItem{item1}, updated)

	_, ok = suite.lru.Update("missing", func(item TestItem) { suite.Fail("updated missing item") })
	suite.False(ok)
}
