package logstash

import (
	"errors"
	"fmt"
	"io"
	"net/http"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

func NewHttpHandler(stash LogStash, r *http.ServeMux) http.Handler {
	r.HandleFunc("GET /logs/{id}", func(w http.ResponseWriter, req *http.Request) {
		var reader LogReader
		var err error

		// Following keeps the response open while the task is still writing.
		if req.URL.Query().Get("follow") == "1" {
			reader, err = stash.Follow(req.Context(), req.PathValue("id"))
		} else {
			reader, err = stash.Read(req.PathValue("id"))
		}
		if errors.Is(err, ErrInvalidLogId) {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusNotFound)
			return
		}
		defer reader.Close()

		w.Header().Set("Content-Type", "text/plain")
		w.WriteHeader(http.StatusOK)
		flusher := http.NewResponseController(w)

		for {
			record, err := reader.ReadLine()
			if err == io.EOF {
				return
			}

			if err != nil {
				// The status is already sent, so there is nowhere to report
				// this but the log. Debug, not Error: the common cause is a
				// worker dying mid-record (io.ErrUnexpectedEOF), which is
				// routine and already visible via the task's own status.
				log.Debugf("read - log - id: %s - error: %v", req.PathValue("id"), err)
				return
			}

			// Convert level to string
			level := ""

			switch record.Level {
			case protocol.LogLevel_EXCEPTION:
				level = "EXCEPT"
			default:
				level = record.Level.String()
			}

			ts := record.Time.AsTime().Local()
			line := fmt.Sprintf(
				"%s.%06d [%7s] %s\n",
				ts.Format("2006-01-02 15:04:05"),
				ts.Nanosecond()/1000,
				level,
				record.Message)

			if _, err := w.Write([]byte(line)); err != nil {
				return
			}

			// Push the line out now. A bufio.Writer would only move it into
			// net/http's own buffer, where it would wait for ~4KB of company.
			flusher.Flush()
		}
	})

	return r
}
