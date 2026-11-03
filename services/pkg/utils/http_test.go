package utils

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestHttpLoggerPassesResponseThrough(t *testing.T) {
	handler := HttpLogger(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Test", "value")
		w.WriteHeader(http.StatusCreated)
		w.Write([]byte("body"))
		http.NewResponseController(w).Flush()
	}))

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/", nil))
	assert.Equal(t, http.StatusCreated, recorder.Code)
	assert.Equal(t, "value", recorder.Header().Get("X-Test"))
	assert.Equal(t, "body", recorder.Body.String())
	assert.True(t, recorder.Flushed)
}

func TestStatusRecorder(t *testing.T) {
	for name, test := range map[string]struct {
		handler func(w http.ResponseWriter)
		want    int
	}{
		"nothing written": {func(w http.ResponseWriter) {}, 0},
		"header":          {func(w http.ResponseWriter) { w.WriteHeader(http.StatusNotFound) }, http.StatusNotFound},
		"header twice": {func(w http.ResponseWriter) {
			w.WriteHeader(http.StatusNotFound)
			w.WriteHeader(http.StatusInternalServerError)
		}, http.StatusNotFound},
		"body":          {func(w http.ResponseWriter) { w.Write([]byte("body")) }, http.StatusOK},
		"body, header":  {func(w http.ResponseWriter) { w.Write([]byte("body")); w.WriteHeader(http.StatusNotFound) }, http.StatusOK},
		"flush":         {func(w http.ResponseWriter) { http.NewResponseController(w).Flush() }, http.StatusOK},
		"flush, header": {func(w http.ResponseWriter) { http.NewResponseController(w).Flush(); w.WriteHeader(http.StatusNotFound) }, http.StatusOK},
		"header, body":  {func(w http.ResponseWriter) { w.WriteHeader(http.StatusAccepted); w.Write([]byte("body")) }, http.StatusAccepted},
		"header, flush": {func(w http.ResponseWriter) { w.WriteHeader(http.StatusAccepted); http.NewResponseController(w).Flush() }, http.StatusAccepted},
	} {
		recorder := &statusRecorder{ResponseWriter: httptest.NewRecorder()}
		test.handler(recorder)
		assert.Equal(t, test.want, recorder.status, name)
	}
}
