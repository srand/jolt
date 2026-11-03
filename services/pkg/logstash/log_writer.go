package logstash

import (
	"io"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type LogWriter interface {
	WriteLine(*protocol.LogLine) error
	Close() error
}

type fileLogWriter struct {
	file   utils.File
	stash  *logStash
	stream *logStream
	id     string
	buf    []byte
}

func newFileLogWriter(stash *logStash, stream *logStream, file utils.File, id string) *fileLogWriter {
	return &fileLogWriter{
		file:   file,
		stash:  stash,
		stream: stream,
		id:     id,
	}
}

func (r *fileLogWriter) WriteLine(line *protocol.LogLine) error {
	record, err := appendRecord(r.buf[:0], line)
	if err != nil {
		return err
	}
	r.buf = record

	// Records of other writers of the log must not end up inside this one.
	// Each record is written at the end of the file in a single write, even
	// on file systems that don't implement O_APPEND for every write.
	r.stream.writeMu.Lock()
	_, err = r.file.Seek(0, io.SeekEnd)
	if err == nil {
		_, err = r.file.Write(record)
	}
	r.stream.writeMu.Unlock()
	if err != nil {
		return err
	}

	r.stash.logWritten(r.id)
	return nil
}

func (r *fileLogWriter) Close() error {
	defer r.stash.logClosed(r)
	return r.file.Close()
}

func (r *fileLogWriter) Path() string {
	return r.file.Name()
}
