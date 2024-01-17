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

// An open log file currently being append
//  type logFile struct {
//  	file utils.File
//  }
//
//  func (f *logFile) Size() (int64, error) {
//  	stat, err := f.file.Stat()
//  	if err != nil {
//  		return 0, err
//  	}
//
//  	return stat.Size(), nil
//  }
//
//  func (f *logFile) ReadLine() (*protocol.LogLine, error) {
//  	gob.NewDecoder()
//  }
//
//  // Read at most count number of log lines
//  func (f *logFile) ReadLines(count uint) ([]*protocol.LogLine, error) {
//  	lines := []*protocol.LogLine{}
//
//  	for i := uint(0); i < count; i++ {
//  		var length uint32
//
//  		if err := binary.Read(f.file, binary.LittleEndian, &length); err != nil {
//  			return lines, err
//  		}
//
//  		// Read protobuf data
//  		var data []byte = make([]byte, length)
//  		if _, err := f.file.Read(data); err != nil {
//  			return lines, nil
//  		}
//
//  		// Unmarshal protobuf to struct
//  		var line protocol.LogLine
//  		if err := proto.Unmarshal(data, &line); err != nil {
//  			return lines, nil
//  		}
//
//  		lines = append(lines, &line)
//  	}
//
//  	return lines, nil
//  }
//
//  func (f *logFile) WriteLines(lines []*protocol.LogLine) error {
//  	for _, line := range lines {
//  		data, err := proto.Marshal(line)
//  		if err != nil {
//  			return err
//  		}
//
//  		if err := binary.Write(f.file, binary.LittleEndian, uint32(len(data))); err != nil {
//  			return err
//  		}
//
//  		if _, err = f.file.Write(data); err != nil {
//  			return err
//  		}
//  	}
//  	return nil
//  }
//
//  func (f *logFile) Close() error {
//  	return nil
//  }
//
