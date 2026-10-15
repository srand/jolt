package logstash

import (
	"context"
	"encoding/gob"
	"io"
	"sync"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// Reads a log file like any other reader, except that reaching the end of the
// file is not the end of the stream while a writer is still open: the read
// blocks until more bytes arrive.
//
// The blocking belongs here, underneath the gob decoder, rather than in a retry
// loop around it. A decoder that reads a half-written record fails with
// io.ErrUnexpectedEOF and cannot be resumed, so it must never see a short read.
type tailReader struct {
	ctx   context.Context
	file  utils.File
	stash *logStash
	id    string
}

func (r *tailReader) Read(p []byte) (int, error) {
	for {
		// Take the channel before reading. A write landing between the read and
		// the wait would otherwise go unnoticed, parking us until the next one.
		notify, drained := r.stash.watch(r.id)

		n, err := r.file.Read(p)
		if n > 0 {
			// Deliver what we have, even when the read also reported EOF.
			return n, nil
		}
		if err != nil && err != io.EOF {
			return 0, err
		}
		if drained {
			return 0, io.EOF
		}
		if notify == nil {
			// Defensive: watch() only hands back a nil channel paired with
			// drained == true today, so this should be unreachable. If that
			// pairing ever changes, selecting on a nil channel would park us
			// here until ctx is cancelled rather than fail loudly.
			return 0, io.EOF
		}

		select {
		case <-notify:
		case <-r.ctx.Done():
			return 0, r.ctx.Err()
		}
	}
}

type followLogReader struct {
	decoder   *gob.Decoder
	file      utils.File
	stash     *logStash
	id        string
	closeOnce sync.Once
	closeErr  error
}

func newFollowLogReader(ctx context.Context, stash *logStash, file utils.File, id string) *followLogReader {
	tail := &tailReader{ctx: ctx, file: file, stash: stash, id: id}

	return &followLogReader{
		decoder: gob.NewDecoder(tail),
		file:    file,
		stash:   stash,
		id:      id,
	}
}

func (r *followLogReader) ReadLine() (*protocol.LogLine, error) {
	var line protocol.LogLine

	if err := r.decoder.Decode(&line); err != nil {
		return nil, err
	}

	return &line, nil
}

// Close is idempotent: a reader may be closed more than once in ordinary Go
// usage (an explicit Close plus a deferred one on an error path, say), and a
// second call to dropFollower would corrupt the shared registry's follower
// count for every other follower of the same log. Only the first call does
// anything; later calls replay its result.
func (r *followLogReader) Close() error {
	r.closeOnce.Do(func() {
		r.stash.dropFollower(r.id)
		r.closeErr = r.file.Close()
	})
	return r.closeErr
}
