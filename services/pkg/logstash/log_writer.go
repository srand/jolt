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
	id      string
}

func newFileLogWriter(stash *logStash, file utils.File, id string) *fileLogWriter {
	return &fileLogWriter{
		file:    file,
		encoder: gob.NewEncoder(file),
		stash:   stash,
		id:      id,
	}
}

func (r *fileLogWriter) WriteLine(line *protocol.LogLine) error {
	if err := r.encoder.Encode(line); err != nil {
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
