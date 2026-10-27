package utils

import (
	"net/http"

	"github.com/srand/jolt/scheduler/pkg/log"
)

// Records the status of a response for logging.
type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	if r.status == 0 {
		r.status = status
	}
	r.ResponseWriter.WriteHeader(status)
}

func (r *statusRecorder) Write(data []byte) (int, error) {
	if r.status == 0 {
		r.status = http.StatusOK
	}
	return r.ResponseWriter.Write(data)
}

func (r *statusRecorder) Flush() {
	if r.status == 0 {
		r.status = http.StatusOK
	}
	http.NewResponseController(r.ResponseWriter).Flush()
}

func (r *statusRecorder) Unwrap() http.ResponseWriter {
	return r.ResponseWriter
}

func HttpLogger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		recorder := &statusRecorder{ResponseWriter: w}
		next.ServeHTTP(recorder, r)
		if recorder.status == 0 {
			recorder.status = http.StatusOK
		}
		if recorder.status >= http.StatusInternalServerError {
			log.Errorf("%4s %s %v", r.Method, r.URL, recorder.status)
		}
		log.Tracef("%4s %s %v", r.Method, r.URL, recorder.status)
	})
}
