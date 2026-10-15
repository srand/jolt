package logstash

import (
	"bytes"
	"context"
	"encoding/gob"
	"errors"
	"io"
	"os"
	"testing"
	"time"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/suite"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type FollowTestSuite struct {
	suite.Suite
	config MockLogStashConfig
	fs     utils.Fs
	stash  *logStash
}

func (s *FollowTestSuite) SetupTest() {
	s.config.On("MaxSize").Return(0x100000)
	s.fs = afero.NewMemMapFs()
	s.stash = NewLogStash(&s.config, s.fs).(*logStash)
}

func (s *FollowTestSuite) line(message string) *protocol.LogLine {
	return &protocol.LogLine{
		Level:   protocol.LogLevel_INFO,
		Time:    timestamppb.Now(),
		Message: message,
	}
}

// The result of a background ReadLine call: both the line and the error, so
// callers can tell "ended cleanly with io.EOF" apart from "ended with some
// other error", rather than collapsing every outcome into a nil line.
type followReadResult struct {
	line *protocol.LogLine
	err  error
}

// Reads one line in the background so the test can assert on whether the read
// blocked.
func (s *FollowTestSuite) readAsync(reader LogReader) chan followReadResult {
	out := make(chan followReadResult, 1)
	go func() {
		line, err := reader.ReadLine()
		out <- followReadResult{line: line, err: err}
	}()
	return out
}

func (s *FollowTestSuite) TestFollowEndsImmediatelyOnCompletedLog() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), writer.WriteLine(s.line("only")))
	assert.NoError(s.T(), writer.Close())

	reader, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)
	defer reader.Close()

	line, err := reader.ReadLine()
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), "only", line.Message)

	_, err = reader.ReadLine()
	assert.Equal(s.T(), io.EOF, err)
}

func (s *FollowTestSuite) TestFollowReturnsErrorForMissingLog() {
	_, err := s.stash.Follow(context.Background(), "nosuchlog")
	assert.Error(s.T(), err)

	s.stash.Lock()
	_, tracked := s.stash.streams["nosuchlog"]
	s.stash.Unlock()
	assert.False(s.T(), tracked, "a failed Follow leaked stream state")
}

// Review Focus 1. A reader closed twice must not corrupt the shared
// registry's follower count: an over-decremented count never reaches zero
// again for a real follower, leaking the stream entry forever, and reads as
// "no followers" while a real follower is registered, silently dropping that
// follower's wakeups.
//
// This needs a live second follower and an open writer at the moment of the
// double close: with no other follower, and the writer already closed, the
// stream entry is already gone by the time the second Close runs (releaseLocked
// deletes it once writers == 0 && followers == 0 after the first Close), so
// dropFollower's pre-existing "unknown id" guard — not the fix under test —
// is what the second call hits. That shape passes whether or not Close is
// idempotent, so it would not have caught the defect this test is for.
func (s *FollowTestSuite) TestFollowCloseIsIdempotent() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), writer.WriteLine(s.line("first")))
	defer writer.Close()

	survivor, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)
	defer survivor.Close()

	doubled, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)

	line, err := survivor.ReadLine()
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), "first", line.Message)

	line, err = doubled.ReadLine()
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), "first", line.Message)

	// Close the same follower twice while the survivor and the writer are
	// both still live.
	assert.NoError(s.T(), doubled.Close())
	assert.NoError(s.T(), doubled.Close())

	// State check: the registry must still record exactly the surviving
	// follower, not an over-decremented count. This is what catches the
	// entry-leak/miscount defect directly, independent of timing.
	s.stash.Lock()
	stream, tracked := s.stash.streams["log1"]
	s.stash.Unlock()
	assert.True(s.T(), tracked, "the double close tore down the stream entry the surviving follower still needs")
	if tracked {
		assert.Equal(s.T(), 1, stream.followers, "the double close corrupted the follower count")
	}

	// Behavioural check: the actual user-visible symptom. If the follower
	// count was driven to zero, logWritten's "any followers?" check sees
	// none and never wakes the survivor, so this would park until the
	// writer closes instead of delivering the new line.
	pending := s.readAsync(survivor)

	select {
	case <-pending:
		s.T().Fatal("ReadLine returned before the line was written")
	case <-time.After(100 * time.Millisecond):
	}

	assert.NoError(s.T(), writer.WriteLine(s.line("second")))

	select {
	case result := <-pending:
		assert.NoError(s.T(), result.err)
		assert.NotNil(s.T(), result.line)
		assert.Equal(s.T(), "second", result.line.Message)
	case <-time.After(2 * time.Second):
		s.T().Fatal("the surviving follower stopped receiving lines after an unrelated double close")
	}
}

func (s *FollowTestSuite) TestFollowBlocksThenDeliversNewLine() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), writer.WriteLine(s.line("first")))

	reader, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)
	defer reader.Close()

	line, err := reader.ReadLine()
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), "first", line.Message)

	pending := s.readAsync(reader)

	select {
	case <-pending:
		s.T().Fatal("ReadLine returned at end of log while a writer was open")
	case <-time.After(100 * time.Millisecond):
	}

	assert.NoError(s.T(), writer.WriteLine(s.line("second")))

	select {
	case result := <-pending:
		assert.NoError(s.T(), result.err)
		assert.NotNil(s.T(), result.line)
		assert.Equal(s.T(), "second", result.line.Message)
	case <-time.After(2 * time.Second):
		s.T().Fatal("ReadLine did not resume after a line was written")
	}

	assert.NoError(s.T(), writer.Close())
}

func (s *FollowTestSuite) TestFollowEndsWhenLastWriterCloses() {
	first, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	second, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)

	reader, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)
	defer reader.Close()

	pending := s.readAsync(reader)
	assert.NoError(s.T(), first.Close())

	select {
	case <-pending:
		s.T().Fatal("ReadLine ended while a second writer was still open")
	case <-time.After(100 * time.Millisecond):
	}

	assert.NoError(s.T(), second.Close())

	select {
	case result := <-pending:
		assert.Nil(s.T(), result.line, "expected end of stream, got a line")
		assert.Equal(s.T(), io.EOF, result.err, "expected a clean io.EOF, not some other error")
	case <-time.After(2 * time.Second):
		s.T().Fatal("ReadLine did not end after the last writer closed")
	}
}

// Review Focus 2.
func (s *FollowTestSuite) TestOneFollowerClosingDoesNotEndAnother() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), writer.WriteLine(s.line("first")))
	defer writer.Close()

	keep, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)
	defer keep.Close()

	leave, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)

	line, err := keep.ReadLine()
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), "first", line.Message)
	assert.NoError(s.T(), leave.Close())

	pending := s.readAsync(keep)

	// Give the read a chance to actually park before the line is written, so
	// a passing test proves the surviving follower is woken by the write
	// rather than merely observing a line that was already on disk when it
	// started reading.
	select {
	case <-pending:
		s.T().Fatal("ReadLine returned before the second line was written")
	case <-time.After(100 * time.Millisecond):
	}

	assert.NoError(s.T(), writer.WriteLine(s.line("second")))

	select {
	case result := <-pending:
		assert.NoError(s.T(), result.err)
		assert.NotNil(s.T(), result.line)
		assert.Equal(s.T(), "second", result.line.Message)
	case <-time.After(2 * time.Second):
		s.T().Fatal("the surviving follower stopped receiving lines")
	}
}

// Review Focus 4.
func (s *FollowTestSuite) TestFollowUnblocksOnContextCancel() {
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)
	assert.NoError(s.T(), writer.WriteLine(s.line("first")))
	defer writer.Close()

	ctx, cancel := context.WithCancel(context.Background())

	reader, err := s.stash.Follow(ctx, "log1")
	assert.NoError(s.T(), err)
	defer reader.Close()

	_, err = reader.ReadLine()
	assert.NoError(s.T(), err)

	pending := s.readAsync(reader)
	cancel()

	select {
	case result := <-pending:
		assert.True(s.T(), errors.Is(result.err, context.Canceled),
			"expected the read to unblock because ctx was cancelled, got err=%v", result.err)
	case <-time.After(2 * time.Second):
		s.T().Fatal("a cancelled context left ReadLine blocked")
	}
}

// The reason this design blocks underneath the decoder instead of retrying it:
// a gob record that is only half written must not desync the decoder.
func (s *FollowTestSuite) TestFollowDecodesRecordSplitAcrossWaits() {
	// Produce a byte stream holding two records, and find a split point inside
	// the second one.
	var buf bytes.Buffer
	encoder := gob.NewEncoder(&buf)
	assert.NoError(s.T(), encoder.Encode(s.line("first")))
	mark := buf.Len()
	assert.NoError(s.T(), encoder.Encode(s.line("second")))

	all := buf.Bytes()
	split := mark + (len(all)-mark)/2

	// Register a writer so follow mode blocks, but write the bytes by hand.
	writer, err := s.stash.Append("log1")
	assert.NoError(s.T(), err)

	file, err := s.fs.OpenFile("log1", os.O_WRONLY, 0644)
	assert.NoError(s.T(), err)
	defer file.Close()

	_, err = file.Write(all[:split])
	assert.NoError(s.T(), err)
	s.stash.logWritten("log1")

	reader, err := s.stash.Follow(context.Background(), "log1")
	assert.NoError(s.T(), err)
	defer reader.Close()

	line, err := reader.ReadLine()
	assert.NoError(s.T(), err)
	assert.Equal(s.T(), "first", line.Message)

	pending := s.readAsync(reader)

	select {
	case <-pending:
		s.T().Fatal("ReadLine returned from a half-written record")
	case <-time.After(100 * time.Millisecond):
	}

	_, err = file.Write(all[split:])
	assert.NoError(s.T(), err)
	s.stash.logWritten("log1")

	select {
	case result := <-pending:
		assert.NoError(s.T(), result.err, "the decoder desynced on the split record")
		assert.NotNil(s.T(), result.line, "the decoder desynced on the split record")
		assert.Equal(s.T(), "second", result.line.Message)
	case <-time.After(2 * time.Second):
		s.T().Fatal("ReadLine did not resume once the record was complete")
	}

	assert.NoError(s.T(), writer.Close())
}

func TestFollow(t *testing.T) {
	suite.Run(t, &FollowTestSuite{})
}
