package logstash

import (
	"context"
	"io"
	"os"
	"path/filepath"
	"strings"

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

	// Follow reads a log like Read, but does not end the stream while the log
	// is still being written. It ends when the last writer closes, or when ctx
	// is cancelled.
	Follow(ctx context.Context, id string) (LogReader, error)
}

type logFile struct {
	fs   utils.Fs
	path string
	size int64
}

func canonicalLogPath(path string) string {
	return strings.TrimLeft(filepath.Clean(path), string(filepath.Separator))
}

func newLogFile(fs utils.Fs, path string) *logFile {
	path = canonicalLogPath(path)
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

// Tracks the writers and followers of a single log, so that a follow reader
// can tell "nothing written yet" from "nothing will be written".
type logStream struct {
	writers   int
	followers int
	notify    chan struct{}
}

type logStash struct {
	mu      utils.RWMutex
	config  LogStashConfig
	fs      utils.Fs
	lru     *utils.LRU[*logFile]
	streams map[string]*logStream
}

// Create a new Logstash GRPC interface
func NewLogStash(config LogStashConfig, fs utils.Fs) LogStash {
	stash := &logStash{
		mu:      utils.NewRWMutex(),
		config:  config,
		fs:      fs,
		streams: map[string]*logStream{},
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

func (s *logStash) Lock() {
	s.mu.Lock()
}

func (s *logStash) Unlock() {
	s.mu.Unlock()
}

// Append a log record to the logstash server
func (s *logStash) Append(id string) (LogWriter, error) {
	id = canonicalLogPath(id)
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
	s.streamLocked(id).writers++
	s.Unlock()

	log.Debug("add - log - id:", id)

	return newFileLogWriter(s, file, id), nil
}

// ReadLog reads a log from the logstash server
func (s *logStash) Read(id string) (LogReader, error) {
	id = canonicalLogPath(id)
	file, err := s.fs.Open(id)
	if err != nil {
		return nil, err
	}

	return newFileLogReader(file), nil
}

// Follow reads a log, blocking at the end of the file while it is still
// being written.
func (s *logStash) Follow(ctx context.Context, id string) (LogReader, error) {
	id = canonicalLogPath(id)

	// Register before opening, so a writer closing in between still wakes us.
	s.addFollower(id)

	file, err := s.fs.Open(id)
	if err != nil {
		s.dropFollower(id)
		return nil, err
	}

	return newFollowLogReader(ctx, s, file, id), nil
}

func (s *logStash) logClosed(writer *fileLogWriter) {
	s.Lock()
	defer s.Unlock()

	s.lru.Add(newLogFile(s.fs, writer.Path()))

	stream, ok := s.streams[writer.id]
	if !ok {
		return
	}

	// Refuse to go negative, mirroring dropFollower below. A writer closed
	// twice would otherwise send writers to -1: it would never read back as
	// zero again, so watch would report drained == false forever and every
	// follower of this id - including every future one - would park until
	// its context is cancelled, for the life of the process.
	if stream.writers == 0 {
		return
	}

	stream.writers--
	if stream.writers == 0 {
		// Wake followers so they can see that the log is finished.
		s.wakeLocked(stream)
	}
	s.releaseLocked(writer.id, stream)
}

// Returns the tracking state for id, creating it if absent.
// Callers must hold s.mu.
func (s *logStash) streamLocked(id string) *logStream {
	stream, ok := s.streams[id]
	if !ok {
		stream = &logStream{notify: make(chan struct{})}
		s.streams[id] = stream
	}
	return stream
}

// Wakes everything waiting on the stream by closing the channel it handed out,
// then installs a fresh one for the next wait. Callers must hold s.mu.
func (s *logStash) wakeLocked(stream *logStream) {
	close(stream.notify)
	stream.notify = make(chan struct{})
}

// Forgets a stream once nothing refers to it. Callers must hold s.mu.
func (s *logStash) releaseLocked(id string, stream *logStream) {
	if stream.writers == 0 && stream.followers == 0 {
		delete(s.streams, id)
	}
}

// Returns the channel to wait on for more data, and whether the log is
// drained: no writer is open, so what is on disk is all there will ever be.
func (s *logStash) watch(id string) (<-chan struct{}, bool) {
	id = canonicalLogPath(id)

	s.Lock()
	defer s.Unlock()

	stream, ok := s.streams[id]
	if !ok {
		return nil, true
	}

	return stream.notify, stream.writers == 0
}

func (s *logStash) addFollower(id string) {
	id = canonicalLogPath(id)

	s.Lock()
	defer s.Unlock()
	s.streamLocked(id).followers++
}

func (s *logStash) dropFollower(id string) {
	id = canonicalLogPath(id)

	s.Lock()
	defer s.Unlock()

	stream, ok := s.streams[id]
	if !ok {
		return
	}

	// Refuse to go negative. A follower that drops twice (a double Close, in
	// particular) must not desync the count: an over-decremented counter
	// never reads back as zero for a real follower's dropFollower, which
	// leaks the stream entry forever, and it reads as zero for logWritten's
	// "any followers?" check while a real follower is still registered,
	// silently dropping that follower's wakeups.
	if stream.followers == 0 {
		return
	}

	stream.followers--
	s.releaseLocked(id, stream)
}

// Called after every log line. Runs on the hot path, so it does nothing at all
// unless somebody is actually following the log.
func (s *logStash) logWritten(id string) {
	id = canonicalLogPath(id)

	s.Lock()
	defer s.Unlock()

	stream, ok := s.streams[id]
	if !ok || stream.followers == 0 {
		return
	}

	s.wakeLocked(stream)
}
