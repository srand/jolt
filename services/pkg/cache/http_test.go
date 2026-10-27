package cache

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/stretchr/testify/assert"
)

// The tests use the LRU cache directly, which returns the open file that
// the size is taken from, without the wrapping of the tracking cache.

func TestHttpGetFileSetsContentLength(t *testing.T) {
	c := newTestCache(t).Cache
	data := []byte("file content")

	writer, err := c.WriteFile("file.tar.zst")
	assert.NoError(t, err)
	_, err = writer.Write(data)
	assert.NoError(t, err)
	assert.NoError(t, writer.Close())

	response := httptest.NewRecorder()
	NewHttpHandler(c, nil).ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/files/file.tar.zst", nil))
	assert.Equal(t, http.StatusOK, response.Code)
	assert.Equal(t, strconv.Itoa(len(data)), response.Header().Get("Content-Length"))
	assert.Equal(t, data, response.Body.Bytes())
}

func TestHttpGetObjectSetsContentLength(t *testing.T) {
	c := newTestCache(t).Cache
	data := []byte("object content")
	digest := put(t, c, data)

	response := httptest.NewRecorder()
	NewHttpHandler(c, nil).ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/objects/"+digest, nil))
	assert.Equal(t, http.StatusOK, response.Code)
	assert.Equal(t, strconv.Itoa(len(data)), response.Header().Get("Content-Length"))
	assert.Equal(t, data, response.Body.Bytes())
}

// Clients store artifacts below a directory named after the task.
func TestHttpFileInSubdirectory(t *testing.T) {
	c := newTestCache(t).Cache
	handler := NewHttpHandler(c, nil)
	data := []byte("file content")
	path := "/files/task/file.tar.zst"

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodPut, path, bytes.NewReader(data)))
	assert.Equal(t, http.StatusCreated, response.Code)

	response = httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodHead, path, nil))
	assert.Equal(t, http.StatusOK, response.Code)

	response = httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, path, nil))
	assert.Equal(t, http.StatusOK, response.Code)
	assert.Equal(t, data, response.Body.Bytes())
}
