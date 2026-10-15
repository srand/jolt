package logstash

import (
	"context"
	"encoding/gob"
	"io"

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

		select {
		case <-notify:
		case <-r.ctx.Done():
			return 0, r.ctx.Err()
		}
	}
}

type followLogReader struct {
	decoder *gob.Decoder
	file    utils.File
	stash   *logStash
	id      string
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

func (r *followLogReader) Close() error {
	r.stash.dropFollower(r.id)
	return r.file.Close()
}
