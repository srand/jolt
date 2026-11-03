package logstash

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type LogReader interface {
	ReadLine() (*protocol.LogLine, error)
	Close() error
}

type fileLogReader struct {
	file    utils.File
	records *recordReader
}

func newFileLogReader(file utils.File) *fileLogReader {
	return &fileLogReader{
		file:    file,
		records: newRecordReader(file),
	}
}

func (r *fileLogReader) ReadLine() (*protocol.LogLine, error) {
	return r.records.ReadLine()
}

func (r *fileLogReader) Close() error {
	return r.file.Close()
}
