package logstash

import (
	"encoding/gob"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type LogWriter interface {
	WriteLine(*protocol.LogLine) error
	Close() error
}

type fileLogWriter struct {
	file    utils.File
	encoder *gob.Encoder
	stash   *logStash
}

func newFileLogWriter(stash *logStash, file utils.File) *fileLogWriter {
	return &fileLogWriter{
		file:    file,
		encoder: gob.NewEncoder(file),
		stash:   stash,
	}
}

func (r *fileLogWriter) WriteLine(line *protocol.LogLine) error {
	return r.encoder.Encode(line)
}

func (r *fileLogWriter) Close() error {
	defer r.stash.logClosed(r)
	return r.file.Close()
}

func (r *fileLogWriter) Path() string {
	return r.file.Name()
}
