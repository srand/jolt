package logstash

import (
	"context"
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

// Log ids are task instance UUIDs.
const (
	logId1       = "6f1c2a4e-8b3d-4f5a-9c7e-1d2b3a4c5e6f"
	logId2       = "0a9b8c7d-6e5f-4a3b-8c2d-1e0f9a8b7c6d"
	missingLogId = "3e4d5c6b-7a8f-4e9d-a0b1-c2d3e4f5a6b7"
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
	writer, err := s.stash.Append(logId1)
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1024), 1023)
	writer.Close()
}

func (s *LogStashTestSuite) TestWriteRead() {
	writer, err := s.stash.Append(logId1)
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1000), 1000)
	assert.NoError(s.T(), writer.Close())

	reader, err := s.stash.Read(logId1)
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
	writer, err := s.stash.Append(logId1)
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1000), 1000)
	assert.NoError(s.T(), writer.Close())

	writer, err = s.stash.Append(logId2)
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("2", 1000), 1000)
	assert.NoError(s.T(), writer.Close())

	_, err = s.stash.Read(logId1)
	assert.Error(s.T(), err)

	reader, err := s.stash.Read(logId2)
	assert.NoError(s.T(), err)
	reader.Close()
}

func (s *LogStashTestSuite) TestActiveReopenedLogIsNotEvicted() {
	config := new(MockLogStashConfig)
	config.On("MaxSize").Return(2048)
	fs := afero.NewBasePathFs(afero.NewOsFs(), s.T().TempDir())
	stash := NewLogStash(config, fs)

	writer, err := stash.Append(logId1)
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 100), 1)
	assert.NoError(s.T(), writer.Close())

	// Reopening a completed log must remove it from the LRU for as long as
	// the new appender is active.
	writer, err = stash.Append(logId1)
	assert.NoError(s.T(), err)
	defer writer.Close()

	other, err := stash.Append(logId2)
	assert.NoError(s.T(), err)
	s.writeLines(other, strings.Repeat("2", 100), 100)
	assert.NoError(s.T(), other.Close())

	_, err = fs.Stat(logId1)
	assert.NoError(s.T(), err)
}

func (s *LogStashTestSuite) TestCreate() {
	// Create two log files in the stash
	writer, err := s.stash.Append(logId1)
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("1", 1000), 500)
	assert.NoError(s.T(), writer.Close())

	writer, err = s.stash.Append(logId2)
	assert.NoError(s.T(), err)
	s.writeLines(writer, strings.Repeat("2", 1000), 500)
	assert.NoError(s.T(), writer.Close())

	// Then create a new stash
	stash := NewLogStash(&s.config, s.fs)

	// And verify that both logs where loaded from the
	// filesystem into the cache
	reader, err := stash.Read(logId1)
	assert.NoError(s.T(), err)
	reader.Close()

	reader, err = stash.Read(logId2)
	assert.NoError(s.T(), err)
	reader.Close()
}

func (s *LogStashTestSuite) TestWatchReportsDrainedForUnknownLog() {
	stash := s.stash.(*logStash)

	notify, drained := stash.watch(missingLogId)
	assert.Nil(s.T(), notify)
	assert.True(s.T(), drained)
}

func (s *LogStashTestSuite) TestWatchTracksOpenWriters() {
	stash := s.stash.(*logStash)

	first, err := stash.Append(logId1)
	assert.NoError(s.T(), err)

	_, drained := stash.watch(logId1)
	assert.False(s.T(), drained)

	second, err := stash.Append(logId1)
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), first.Close())

	// One writer is still open, so the log is not drained.
	_, drained = stash.watch(logId1)
	assert.False(s.T(), drained)

	assert.NoError(s.T(), second.Close())

	_, drained = stash.watch(logId1)
	assert.True(s.T(), drained)
}

func (s *LogStashTestSuite) TestCanonicalizesId() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append(strings.ToUpper(logId1))
	assert.NoError(s.T(), err)
	defer writer.Close()

	// Different spellings of the same UUID must resolve to the same log and
	// the same stream, or a follower would silently miss the writer.
	_, err = stash.Read("{" + logId1 + "}")
	assert.NoError(s.T(), err)
	_, drained := stash.watch(logId1)
	assert.False(s.T(), drained)
}

func (s *LogStashTestSuite) TestRejectsInvalidId() {
	for _, id := range []string{"", "log1", "../" + logId1, "/" + logId1, logId1 + "/x", "../../etc/passwd"} {
		_, err := s.stash.Append(id)
		assert.ErrorIs(s.T(), err, ErrInvalidLogId, id)
		_, err = s.stash.Read(id)
		assert.ErrorIs(s.T(), err, ErrInvalidLogId, id)
		_, err = s.stash.Follow(context.Background(), id)
		assert.ErrorIs(s.T(), err, ErrInvalidLogId, id)
	}

	// Nothing may have been created for a rejected id.
	files, err := afero.ReadDir(s.fs, ".")
	assert.NoError(s.T(), err)
	assert.Empty(s.T(), files)
}

func (s *LogStashTestSuite) TestWriteWakesWaiters() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append(logId1)
	assert.NoError(s.T(), err)
	defer writer.Close()

	// A registered follower is what makes notification observable.
	stash.addFollower(logId1)
	defer stash.dropFollower(logId1)

	notify, _ := stash.watch(logId1)
	s.writeLines(writer, "line", 1)

	select {
	case <-notify:
	case <-time.After(2 * time.Second):
		s.T().Fatal("writing a line did not wake waiters")
	}
}

func (s *LogStashTestSuite) TestLastWriterCloseWakesWaiters() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append(logId1)
	assert.NoError(s.T(), err)

	stash.addFollower(logId1)
	defer stash.dropFollower(logId1)

	notify, _ := stash.watch(logId1)
	assert.NoError(s.T(), writer.Close())

	select {
	case <-notify:
	case <-time.After(2 * time.Second):
		s.T().Fatal("closing the last writer did not wake waiters")
	}
}

func (s *LogStashTestSuite) TestWritingWithoutFollowersDoesNotBlock() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append(logId1)
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

	writer, err := stash.Append(logId1)
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), writer.Close())

	stash.Lock()
	_, tracked := stash.streams[logId1]
	stash.Unlock()
	assert.False(s.T(), tracked, "stream state leaked after the last writer closed")
}

// A writer closed twice must not corrupt the shared registry's writer count,
// the same way a follower closed twice must not (see log_reader_follow_test.go's
// TestFollowCloseIsIdempotent). An over-decremented count never reads back as
// zero again, leaking the stream entry forever and leaving watch reporting
// drained == false permanently - parking every follower of this id, forever.
//
// This needs a live follower at the moment of the double close: with no
// follower registered, the first Close already releases the stream entry
// (releaseLocked deletes it once writers == 0 && followers == 0), so the
// second Close hits the pre-existing "unknown id" guard rather than the floor
// under test.
func (s *LogStashTestSuite) TestWriterCloseIsIdempotent() {
	stash := s.stash.(*logStash)

	writer, err := stash.Append(logId1)
	assert.NoError(s.T(), err)

	stash.addFollower(logId1)
	defer stash.dropFollower(logId1)

	assert.NoError(s.T(), writer.Close())
	assert.NoError(s.T(), writer.Close())

	stash.Lock()
	stream, tracked := stash.streams[logId1]
	stash.Unlock()
	assert.True(s.T(), tracked, "the double close tore down the stream entry the follower still needs")
	if tracked {
		assert.Equal(s.T(), 0, stream.writers, "the double close drove the writer count negative")
	}

	// Behavioural check: watch must be able to report "drained" again once
	// the (single) real writer has closed, even after the extra Close.
	_, drained := stash.watch(logId1)
	assert.True(s.T(), drained, "watch never reports drained after a writer double close, parking followers forever")
}

func TestLogStash(t *testing.T) {
	suite.Run(t, &LogStashTestSuite{})
}

// A zero budget is zero capacity, not unbounded: the LRU trims as soon as a
// closed log is handed back to it, and eviction unlinks the file. The symptom
// is deliberately confusing, because a log stays readable while its writer is
// open -- Append holds it out of the LRU -- so only completed tasks lose their
// logs. The scheduler's configuration default exists to avoid this; this test
// pins the behaviour it is defaulting away from.
func TestZeroSizeStashDiscardsLogsOnceTheWriterCloses(t *testing.T) {
	config := new(MockLogStashConfig)
	config.On("MaxSize").Return(0)
	stash := NewLogStash(config, afero.NewMemMapFs())

	writer, err := stash.Append(logId1)
	assert.NoError(t, err)
	assert.NoError(t, writer.WriteLine(testLine("only")))

	// Still readable: the open writer keeps it out of the cache.
	reader, err := stash.Read(logId1)
	assert.NoError(t, err)
	assert.NoError(t, reader.Close())

	assert.NoError(t, writer.Close())

	_, err = stash.Read(logId1)
	assert.Error(t, err, "a zero-budget stash retains nothing once the writer closes")
}
