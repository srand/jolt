package cache

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/utils"
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

func TestHttpFindObjects(t *testing.T) {
	c := newTestCache(t).Cache
	handler := NewHttpHandler(c, nil)
	present := put(t, c, []byte("present"))
	missing := blake3Digest([]byte("missing"))

	find := func(query string) FindBlobsResponse {
		body := fmt.Sprintf(`{"blobs": [%q, %q]}`, present, missing)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/objects"+query, strings.NewReader(body)))
		assert.Equal(t, http.StatusOK, response.Code, query)
		result := FindBlobsResponse{}
		assert.NoError(t, json.NewDecoder(response.Body).Decode(&result), query)
		return result
	}
	digests := func(digests []utils.Digest) []string {
		result := []string{}
		for _, digest := range digests {
			result = append(result, digest.String())
		}
		return result
	}

	for query, want := range map[string]struct{ present, missing []string }{
		"":                  {[]string{present}, []string{missing}},
		"?present":          {[]string{present}, []string{}},
		"?missing":          {[]string{}, []string{missing}},
		"?present&missing":  {[]string{present}, []string{missing}},
		"?missing&present=": {[]string{present}, []string{missing}},
	} {
		result := find(query)
		assert.Equal(t, want.present, digests(result.Present), query)
		assert.Equal(t, want.missing, digests(result.Missing), query)
	}
}

func TestHttpFindFiles(t *testing.T) {
	c := newTestCache(t).Cache
	handler := NewHttpHandler(c, nil)

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodPut, "/files/task/present.tar", strings.NewReader("data")))
	assert.Equal(t, http.StatusCreated, response.Code)

	for query, want := range map[string]FindFilesResponse{
		"":                 {Present: []string{"task/present.tar"}, Missing: []string{"task/missing.tar"}},
		"?present":         {Present: []string{"task/present.tar"}},
		"?missing":         {Missing: []string{"task/missing.tar"}},
		"?present&missing": {Present: []string{"task/present.tar"}, Missing: []string{"task/missing.tar"}},
	} {
		body := `{"files": ["task/present.tar", "task/missing.tar"]}`
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/files"+query, strings.NewReader(body)))
		assert.Equal(t, http.StatusOK, response.Code, query)
		result := FindFilesResponse{}
		assert.NoError(t, json.NewDecoder(response.Body).Decode(&result), query)
		assert.Equal(t, want, result, query)
	}
}

func TestHttpFindWithoutBody(t *testing.T) {
	// An empty request finds nothing, while a malformed one is an error.
	handler := NewHttpHandler(newTestCache(t).Cache, nil)
	for _, path := range []string{"/objects", "/files"} {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(http.MethodPost, path, nil))
		assert.Equal(t, http.StatusOK, response.Code, path)

		response = httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(http.MethodPost, path, strings.NewReader("{")))
		assert.Equal(t, http.StatusBadRequest, response.Code, path)
	}
}

func TestHttpObjects(t *testing.T) {
	c := newTestCache(t).Cache
	handler := NewHttpHandler(c, nil)
	data := []byte("object content")
	digest := blake3Digest(data)

	request := func(method, path string, body []byte) *httptest.ResponseRecorder {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(method, path, bytes.NewReader(body)))
		return response
	}

	assert.Equal(t, http.StatusNotFound, request(http.MethodHead, "/objects/"+digest, nil).Code)
	assert.Equal(t, http.StatusNotFound, request(http.MethodGet, "/objects/"+digest, nil).Code)

	// Objects must have the content of their digest
	assert.NotEqual(t, http.StatusCreated, request(http.MethodPut, "/objects/"+digest, []byte("other content")).Code)
	assert.Equal(t, http.StatusNotFound, request(http.MethodHead, "/objects/"+digest, nil).Code)

	assert.Equal(t, http.StatusCreated, request(http.MethodPut, "/objects/"+digest, data).Code)
	response := request(http.MethodHead, "/objects/"+digest, nil)
	assert.Equal(t, http.StatusOK, response.Code)
	assert.Equal(t, strconv.Itoa(len(data)), response.Header().Get("Content-Length"))

	for _, method := range []string{http.MethodHead, http.MethodGet, http.MethodPut} {
		assert.Equal(t, http.StatusBadRequest, request(method, "/objects/sha1:xyz", nil).Code, method)
	}
}

func TestHttpFileNotFound(t *testing.T) {
	handler := NewHttpHandler(newTestCache(t).Cache, nil)
	for _, method := range []string{http.MethodHead, http.MethodGet} {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(method, "/files/task/missing.tar", nil))
		assert.Equal(t, http.StatusNotFound, response.Code, method)
	}
}

func TestHttpCacheMetrics(t *testing.T) {
	c := newTestCache(t).Cache
	handler := NewHttpHandler(c, NewCacheService(c, 64<<20))
	put(t, c, []byte("12345"))
	put(t, c, []byte("123"))
	c.HasObject(utils.NewDigest(utils.Sha1Algorithm, "356a192b7913b04c54574d18c28d46e6395428ab"))

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	assert.Equal(t, http.StatusOK, response.Code)
	assert.Equal(t, "text/plain; charset=UTF-8", response.Header().Get("Content-Type"))
	body := response.Body.String()

	for _, metric := range []struct {
		name, kind string
		value      int64
	}{
		{"jolt_cache_artifacts", "gauge", 2},
		{"jolt_cache_evictions_total", "counter", 0},
		{"jolt_cache_hits_total", "counter", 0},
		{"jolt_cache_misses_total", "counter", 1},
		{"jolt_cache_size_bytes", "gauge", 8},
	} {
		assert.Contains(t, body, fmt.Sprintf("# TYPE %s %s\n# HELP %s ", metric.name, metric.kind, metric.name))
		assert.Contains(t, body, fmt.Sprintf("\n%s %d\n", metric.name, metric.value))
	}
	assert.True(t, strings.HasPrefix(body, "# TYPE jolt_cache_artifacts gauge\n"))
	assert.Contains(t, body, "\njolt_cache_hastree_requests_total 0\n")
}
