package logstash

import (
	"io"
	"os"
	"sync"

	"github.com/spf13/afero"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type LogStashConfig interface {
	// Get the maximum allowed size of the stash
	// If the stash is larger than this, the oldest entries will be removed.
	// If this is 0, the stash will be unbounded.
	MaxSize() int64
}

type LogStash interface {
	// Append a log record to the logstash server
	Append(id string) (LogWriter, error)

	// ReadLog reads a log from the logstash server
	Read(id string) (LogReader, error)
}

type logFile struct {
	fs   utils.Fs
	path string
	size int64
}

func newLogFile(fs utils.Fs, path string) *logFile {
	var size int64 = 0

	st, err := fs.Stat(path)
	if err != nil {
		size = 0
	} else {
		size = st.Size()
	}

	log := &logFile{
		fs:   fs,
		path: path,
		size: size,
	}

	return log
}

func (f *logFile) Path() string {
	return f.path
}

func (f *logFile) Size() int64 {
	return f.size
}

func (f *logFile) Unlink() error {
	return f.fs.Remove(f.path)
}

type logStash struct {
	sync.RWMutex
	config LogStashConfig
	fs     utils.Fs
	lru    *utils.LRU[*logFile]
}

// Create a new Logstash GRPC interface
func NewLogStash(config LogStashConfig, fs utils.Fs) LogStash {
	stash := &logStash{
		config: config,
		fs:     fs,
	}

	stash.lru = utils.NewLRU[*logFile](config.MaxSize(), func(item *logFile) bool {
		log.Debug("del - log - id:", item.Path())
		item.Unlink()
		return true
	})

	// Load existing log files into LRU
	logCount := 0

	afero.Walk(fs, ".", func(path string, info os.FileInfo, err error) error {
		if path == "." {
			return nil
		}

		stash.lru.Add(newLogFile(fs, path))
		logCount++
		return nil
	})

	log.Infof("Loaded %d log files into logstash LRU cache. Size: %s / %s",
		logCount, utils.HumanByteSize(stash.lru.Size()), utils.HumanByteSize(config.MaxSize()))

	return stash
}

// Append a log record to the logstash server
func (s *logStash) Append(id string) (LogWriter, error) {
	var file utils.File

	file, err := s.fs.Open(id)
	if err != nil {
		file, err = s.fs.Create(id)
		if err != nil {
			return nil, err
		}
	} else {
		if _, err := file.Seek(0, io.SeekEnd); err != nil {
			file.Close()
			return nil, err
		}
	}

	s.Lock()
	s.lru.Remove(id)
	s.Unlock()

	log.Debug("add - log - id:", id)

	return newFileLogWriter(s, file), nil
}

// ReadLog reads a log from the logstash server
func (s *logStash) Read(id string) (LogReader, error) {
	file, err := s.fs.Open(id)
	if err != nil {
		return nil, err
	}

	return newFileLogReader(file), nil
}

func (s *logStash) logClosed(writer *fileLogWriter) {
	s.Lock()
	defer s.Unlock()

	s.lru.Add(newLogFile(s.fs, writer.Path()))
}
