package logstash

import (
	"strings"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

type MockLogReader struct {
	mock.Mock
}

func (r *MockLogReader) ReadLine() (*protocol.LogLine, error) {
	args := r.Called()
	line := args.Get(0)
	err := args.Error(1)

	if line != nil {
		return line.(*protocol.LogLine), err
	}
	return nil, err
}

func (r *MockLogReader) Close() error {
	args := r.Called()
	return args.Error(0)
}

func TestLogFilter(t *testing.T) {
	mockLine1 := &protocol.LogLine{Level: protocol.LogLevel_DEBUG, Message: "Hello"}
	mockLine2 := &protocol.LogLine{Level: protocol.LogLevel_DEBUG, Message: "Jello"}
	reader := &MockLogReader{}
	reader.On("ReadLine").Return(mockLine2, nil).Twice()
	reader.On("ReadLine").Return(mockLine1, nil)

	filter := NewFilteredLogReader(reader)

	line, err := filter.ReadLine()
	assert.NoError(t, err)
	assert.Equal(t, line, mockLine2)

	filter.AddFilter(func(ll *protocol.LogLine) bool {
		return strings.HasPrefix(ll.Message, "Hello")
	})

	line, err = filter.ReadLine()
	assert.NoError(t, err)
	assert.Equal(t, line, mockLine1)
}
