package logstash

import (
	"io"
	"strings"
	"testing"
	"time"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/suite"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// Mock config
type MockLogStashConfig struct {
	mock.Mock
}

func (c *MockLogStashConfig) MaxSize() int64 {
	a := c.Called()
	return int64(a.Int(0))
}

type LogStashTestSuite struct {
	suite.Suite
	config MockLogStashConfig
	fs     utils.Fs
	stash  LogStash
}

func (s *LogStashTestSuite) SetupTest() {
	s.config.On("MaxSize").Return(0x100000)
	s.fs = afero.NewMemMapFs()

	s.stash = NewLogStash(&s.config, s.fs)
}

func (s *LogStashTestSuite) writeLines(writer LogWriter, data string, count int) {
	for i := 0; i < count; i++ {
		writer.WriteLine(
			&protocol.LogLine{
				Level:   protocol.LogLevel_INFO,
				Time:    timestamppb.Now(),
				Message: data,
			},
		)
	}
}

func (s *LogStashTestSuite) TestEviction() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1024), 1023)
	writer.Close()
}

func (s *LogStashTestSuite) TestWriteRead() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1000), 1000)
	assert.NoError(s.T(), writer.Close())

	reader, err := s.stash.Read("log1")
	assert.NoError(s.T(), err)
	defer reader.Close()

	count := 0
	for {
		line, err := reader.ReadLine()
		if err == io.EOF {
			break
		}
		assert.Equal(s.T(), line.Message, strings.Repeat("1", 1000))

		count++
	}
	assert.Equal(s.T(), 1000, count)
}

func (s *LogStashTestSuite) TestEvict() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1000), 1000)
	assert.NoError(s.T(), writer.Close())

	writer, err = s.stash.Append("log2")
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("2", 1000), 1000)
	assert.NoError(s.T(), writer.Close())

	_, err = s.stash.Read("log1")
	assert.Error(s.T(), err)

	reader, err := s.stash.Read("log2")
	assert.NoError(s.T(), err)
	reader.Close()
}

func (s *LogStashTestSuite) TestActiveReopenedLogIsNotEvicted() {
	config := new(MockLogStashConfig)
	config.On("MaxSize").Return(2048)
	fs := afero.NewBasePathFs(afero.NewOsFs(), s.T().TempDir())
	stash := NewLogStash(config, fs)

	writer, err := stash.Append("log1")
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 100), 1)
	assert.NoError(s.T(), writer.Close())

	// Reopening a completed log must remove it from the LRU for as long as
	// the new appender is active.
	writer, err = stash.Append("log1")
	assert.NoError(s.T(), err)
	defer writer.Close()

	other, err := stash.Append("log2")
	assert.NoError(s.T(), err)
	s.writeLines(other, strings.Repeat("2", 100), 100)
	assert.NoError(s.T(), other.Close())

	_, err = fs.Stat("log1")
	assert.NoError(s.T(), err)
}

func (s *LogStashTestSuite) TestCreate() {
	// Create two log files in the stash
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1000), 500)
	assert.NoError(s.T(), writer.Close())

	writer, err = s.stash.Append("log2")
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("2", 1000), 500)
	assert.NoError(s.T(), writer.Close())

	// Then create a new stash
	stash := NewLogStash(&s.config, s.fs)

	// And verify that both logs where loaded from the
	// filesystem into the cache
	reader, err := stash.Read("log1")
	assert.NoError(s.T(), err)
	reader.Close()

	reader, err = stash.Read("log2")
	assert.NoError(s.T(), err)
	reader.Close()
}

func (s *LogStashTestSuite) TestWatchReportsDrainedForUnknownLog() {
	stash := s.stash.(*logStash)

	notify, drained := stash.watch("nosuchlog")
	assert.Nil(s.T(), notify)
	assert.True(s.T(), drained)
}

func (s *LogStashTestSuite) TestWatchTracksOpenWriters() {
	stash := s.stash.(*logStash)

	first, err := stash.Append("log1")
	assert.NoError(s.T(), err)

	_, drained := stash.watch("log1")
	assert.False(s.T(), drained)

	second, err := stash.Append("log1")
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), first.Close())

	// One writer is still open, so the log is not drained.
	_, drained = stash.watch("log1")
	assert.False(s.T(), drained)

	assert.NoError(s.T(), second.Close())

	_, drained = stash.watch("log1")
	assert.True(s.T(), drained)
}

func (s *LogStashTestSuite) TestWriteWakesWaiters() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append("log1")
	assert.NoError(s.T(), err)
	defer writer.Close()

	// A registered follower is what makes notification observable.
	stash.addFollower("log1")
	defer stash.dropFollower("log1")

	notify, _ := stash.watch("log1")
	s.writeLines(writer, "line", 1)

	select {
	case <-notify:
	case <-time.After(2 * time.Second):
		s.T().Fatal("writing a line did not wake waiters")
	}
}

func (s *LogStashTestSuite) TestLastWriterCloseWakesWaiters() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append("log1")
	assert.NoError(s.T(), err)

	stash.addFollower("log1")
	defer stash.dropFollower("log1")

	notify, _ := stash.watch("log1")
	assert.NoError(s.T(), writer.Close())

	select {
	case <-notify:
	case <-time.After(2 * time.Second):
		s.T().Fatal("closing the last writer did not wake waiters")
	}
}

func (s *LogStashTestSuite) TestWritingWithoutFollowersDoesNotBlock() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append("log1")
	assert.NoError(s.T(), err)

	// Nobody is following, so notification must do nothing at all. If this
	// ever blocks or panics, every task on the scheduler pays for it.
	done := make(chan struct{})
	go func() {
		s.writeLines(writer, "line", 1000)
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		s.T().Fatal("writing lines blocked with no follower registered")
	}

	assert.NoError(s.T(), writer.Close())
}

func (s *LogStashTestSuite) TestStreamStateIsReleasedWhenIdle() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append("log1")
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), writer.Close())

	stash.Lock()
	_, tracked := stash.streams["log1"]
	stash.Unlock()
	assert.False(s.T(), tracked, "stream state leaked after the last writer closed")
}

func TestLogStash(t *testing.T) {
	suite.Run(t, &LogStashTestSuite{})
}
