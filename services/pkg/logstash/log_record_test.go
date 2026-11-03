package logstash

import (
	"bytes"
	"encoding/binary"
	"io"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func TestRecords(t *testing.T) {
	lines := []*protocol.LogLine{
		{Level: protocol.LogLevel_INFO, Time: timestamppb.Now(), Message: "first"},
		{},
		{Level: protocol.LogLevel_ERROR, Message: string(bytes.Repeat([]byte("x"), 300)), Context: "task"},
	}
	var data []byte
	for _, line := range lines {
		var err error
		data, err = appendRecord(data, line)
		assert.NoError(t, err)
	}

	reader := newRecordReader(bytes.NewReader(data))
	for _, want := range lines {
		line, err := reader.ReadLine()
		assert.NoError(t, err)
		assert.True(t, proto.Equal(want, line), "%v != %v", want, line)
	}
	_, err := reader.ReadLine()
	assert.Equal(t, io.EOF, err)
}

func TestRecordFormat(t *testing.T) {
	// A record is the length of the encoded line, then the line.
	line := &protocol.LogLine{Message: "hello"}
	encoded, err := proto.Marshal(line)
	assert.NoError(t, err)

	record, err := appendRecord([]byte("prefix"), line)
	assert.NoError(t, err)
	assert.Equal(t, append(append([]byte("prefix"), byte(len(encoded))), encoded...), record)
}

func TestTruncatedRecords(t *testing.T) {
	record, err := appendRecord(nil, &protocol.LogLine{Message: string(bytes.Repeat([]byte("x"), 300))})
	assert.NoError(t, err)

	// Within the length, and within the line
	for _, size := range []int{1, 2, 10, len(record) - 1} {
		_, err := newRecordReader(bytes.NewReader(record[:size])).ReadLine()
		assert.Equal(t, io.ErrUnexpectedEOF, err, size)
	}
}

func TestInvalidRecords(t *testing.T) {
	tooLong := binary.AppendUvarint(nil, maxRecordSize+1)
	_, err := newRecordReader(bytes.NewReader(append(tooLong, 0))).ReadLine()
	assert.ErrorContains(t, err, "out of range")

	maxLength := binary.AppendUvarint(nil, maxRecordSize)
	_, err = newRecordReader(bytes.NewReader(maxLength)).ReadLine()
	assert.Equal(t, io.ErrUnexpectedEOF, err)

	// A line that isn't protobuf
	_, err = newRecordReader(bytes.NewReader([]byte{2, 0xff, 0xff})).ReadLine()
	assert.ErrorContains(t, err, "invalid log record")
}
