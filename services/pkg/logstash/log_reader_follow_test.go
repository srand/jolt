package logstash

import (
	"bytes"
	"context"
	"encoding/gob"
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

// Reads one line in the background so the test can assert on whether the read
// blocked.
func (s *FollowTestSuite) readAsync(reader LogReader) chan *protocol.LogLine {
	out := make(chan *protocol.LogLine, 1)
	go func() {
		line, err := reader.ReadLine()
		if err != nil {
			out <- nil
			return
		}
		out <- line
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
	case line := <-pending:
		assert.NotNil(s.T(), line)
		assert.Equal(s.T(), "second", line.Message)
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
	case line := <-pending:
		assert.Nil(s.T(), line, "expected end of stream, got a line")
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
	assert.NoError(s.T(), writer.WriteLine(s.line("second")))

	select {
	case line := <-pending:
		assert.NotNil(s.T(), line)
		assert.Equal(s.T(), "second", line.Message)
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
	case <-pending:
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
	case line := <-pending:
		assert.NotNil(s.T(), line, "the decoder desynced on the split record")
		assert.Equal(s.T(), "second", line.Message)
	case <-time.After(2 * time.Second):
		s.T().Fatal("ReadLine did not resume once the record was complete")
	}

	assert.NoError(s.T(), writer.Close())
}

func TestFollow(t *testing.T) {
	suite.Run(t, &FollowTestSuite{})
}
