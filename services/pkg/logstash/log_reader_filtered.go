package logstash

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

type LogFilterFunc func(*protocol.LogLine) bool

type filteredLogReader struct {
	reader  LogReader
	filters []LogFilterFunc
}

func NewFilteredLogReader(reader LogReader) *filteredLogReader {
	return &filteredLogReader{
		reader: reader,
	}
}

func (r *filteredLogReader) AddFilter(filter LogFilterFunc) {
	r.filters = append(r.filters, filter)
}

func (r *filteredLogReader) Match(line *protocol.LogLine) bool {
	for _, filter := range r.filters {
		if !filter(line) {
			return false
		}
	}

	return true
}

func (r *filteredLogReader) ReadLine() (*protocol.LogLine, error) {
	for {
		line, err := r.reader.ReadLine()
		if err != nil {
			return nil, err
		}

		if r.Match(line) {
			return line, nil
		}
	}
}
