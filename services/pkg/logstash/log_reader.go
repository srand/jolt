package logstash

import (
	"encoding/gob"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type LogReader interface {
	ReadLine() (*protocol.LogLine, error)
	Close() error
}

type fileLogReader struct {
	file    utils.File
	decoder *gob.Decoder
}

func newFileLogReader(file utils.File) *fileLogReader {
	return &fileLogReader{
		file:    file,
		decoder: gob.NewDecoder(file),
	}
}

func (r *fileLogReader) ReadLine() (*protocol.LogLine, error) {
	var line protocol.LogLine

	if err := r.decoder.Decode(&line); err != nil {
		return nil, err
	}

	return &line, nil
}

func (r *fileLogReader) Close() error {
	return r.file.Close()
}
