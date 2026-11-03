package logstash

import (
	"bufio"
	"encoding/binary"
	"fmt"
	"io"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/protobuf/proto"
)

// Logs are files of records, each a LogLine encoded as protobuf and preceded
// by its length as a varint. Records don't depend on each other, so a log can
// be appended to by more than one writer, one after the other or at the same
// time, and read from the start of any record.

// Upper bound for the length of a record. Larger lengths are only found in
// corrupt files, and must not be used to size an allocation.
const maxRecordSize = 16 << 20

// Returns buf with the record of line appended.
func appendRecord(buf []byte, line *protocol.LogLine) ([]byte, error) {
	buf = binary.AppendUvarint(buf, uint64(proto.Size(line)))
	return proto.MarshalOptions{}.MarshalAppend(buf, line)
}

type recordReader struct {
	reader *bufio.Reader
}

func newRecordReader(reader io.Reader) *recordReader {
	return &recordReader{reader: bufio.NewReader(reader)}
}

// Returns the next line, io.EOF at the end of the last record, and
// io.ErrUnexpectedEOF if the last record is incomplete.
func (r *recordReader) ReadLine() (*protocol.LogLine, error) {
	size, err := binary.ReadUvarint(r.reader)
	if err != nil {
		return nil, err
	}
	if size > maxRecordSize {
		return nil, fmt.Errorf("log record length out of range: %d", size)
	}

	data := make([]byte, size)
	if _, err := io.ReadFull(r.reader, data); err != nil {
		if err == io.EOF {
			err = io.ErrUnexpectedEOF
		}
		return nil, err
	}

	line := &protocol.LogLine{}
	if err := proto.Unmarshal(data, line); err != nil {
		return nil, fmt.Errorf("invalid log record: %w", err)
	}
	return line, nil
}
