package logstash

import (
	"io"
	"strings"
	"testing"

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

func TestLogStash(t *testing.T) {
	suite.Run(t, &LogStashTestSuite{})
}
