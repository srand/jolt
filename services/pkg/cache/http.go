package cache

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// Represents an error response.
type Error struct {
	Message string `json:"message"`
}

// writeJSON writes a JSON response.
func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(value)
}

// newError writes an error response.
func newError(w http.ResponseWriter, r *http.Request, err error) {
	if errors.Is(err, utils.ErrNotFound) {
		writeJSON(w, http.StatusNotFound, &Error{Message: err.Error()})
		return
	}

	if errors.Is(err, utils.ErrBadRequest) {
		writeJSON(w, http.StatusBadRequest, &Error{Message: err.Error()})
		return
	}

	log.Error(r.URL, err)
	writeJSON(w, http.StatusInternalServerError, &Error{Message: err.Error()})
}

// bindJSON decodes a JSON request body. An empty body leaves value unchanged.
func bindJSON(r *http.Request, value any) error {
	if err := json.NewDecoder(r.Body).Decode(value); err != nil && err != io.EOF {
		return err
	}
	return nil
}

// FindFilesRequest represents a request to find files.
type FindFilesRequest struct {
	Files []string `json:"files"`
}

// FindFilesResponse represents a response to a find files request.
type FindFilesResponse struct {
	// The files that are missing.
	Missing []string `json:"missing,omitempty"`

	// The files that are present.
	Present []string `json:"present,omitempty"`
}

// FindBlobsRequest represents a request to find objects.
type FindBlobsRequest struct {
	Blobs []utils.Digest `json:"blobs"`
}

// FindBlobsResponse represents a response to a find objects request.
type FindBlobsResponse struct {
	// The objects that are missing.
	Missing []utils.Digest `json:"missing"`

	// The objects that are present.
	Present []utils.Digest `json:"present"`
}

// NewHttpHandler creates a new HTTP handler for the cache. Its metrics
// include statistics of the gRPC service, if one is given.
// Sets the Content-Length of a response from the file being sent, so that
// clients can show the progress of the download. The size is taken from the
// open file instead of looking up the cache entry again, which would count
// as another cache hit.
func setContentLength(w http.ResponseWriter, reader io.Reader) {
	file, ok := reader.(interface{ Stat() (os.FileInfo, error) })
	if !ok {
		return
	}
	if info, err := file.Stat(); err == nil && info.Mode().IsRegular() {
		w.Header().Set("Content-Length", fmt.Sprint(info.Size()))
	}
}

func NewHttpHandler(cache Cache, service CacheGrpcService) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("HEAD /objects/{digest}", func(w http.ResponseWriter, r *http.Request) {
		digest, err := utils.ParseDigest(r.PathValue("digest"))
		if err != nil {
			newError(w, r, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
			return
		}

		if info := cache.HasObject(digest); info != nil {
			w.Header().Set("Content-Length", fmt.Sprint(info.Size()))
			writeJSON(w, http.StatusOK, nil)
			return
		}

		newError(w, r, utils.ErrNotFound)
	})

	mux.HandleFunc("GET /objects/{digest}", func(w http.ResponseWriter, r *http.Request) {
		digest, err := utils.ParseDigest(r.PathValue("digest"))
		if err != nil {
			newError(w, r, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
			return
		}

		reader, err := cache.ReadObject(digest)
		if err != nil {
			newError(w, r, err)
			return
		}
		defer reader.Close()

		setContentLength(w, reader)

		if _, err := io.Copy(w, reader); err != nil {
			log.Error(r.URL, err)
		}
	})

	mux.HandleFunc("POST /objects", func(w http.ResponseWriter, r *http.Request) {
		missing := r.URL.Query().Has("missing")
		present := r.URL.Query().Has("present")
		if !missing && !present {
			missing = true
			present = true
		}

		request := FindBlobsRequest{}
		response := FindBlobsResponse{}

		if err := bindJSON(r, &request); err != nil {
			newError(w, r, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
			return
		}

		for _, digest := range request.Blobs {
			info := cache.HasObject(digest)

			if present && info != nil {
				response.Present = append(response.Present, digest)
			}

			if missing && info == nil {
				response.Missing = append(response.Missing, digest)
			}
		}

		writeJSON(w, http.StatusOK, response)
	})

	mux.HandleFunc("PUT /objects/{digest}", func(w http.ResponseWriter, r *http.Request) {
		digest, err := utils.ParseDigest(r.PathValue("digest"))
		if err != nil {
			newError(w, r, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
			return
		}

		writer, err := cache.WriteObject(digest)
		if err != nil {
			newError(w, r, err)
			return
		}

		if _, err := io.Copy(writer, r.Body); err != nil {
			writer.Discard()
			newError(w, r, err)
			return
		}

		if err := writer.Close(); err != nil {
			newError(w, r, err)
			return
		}

		writeJSON(w, http.StatusCreated, nil)
	})

	mux.HandleFunc("HEAD /files/{path}", func(w http.ResponseWriter, r *http.Request) {
		if info := cache.HasFile(r.PathValue("path")); info != nil {
			w.Header().Set("Content-Length", fmt.Sprint(info.Size()))
			writeJSON(w, http.StatusOK, nil)
			return
		}

		newError(w, r, utils.ErrNotFound)
	})

	mux.HandleFunc("GET /files/{path}", func(w http.ResponseWriter, r *http.Request) {
		reader, err := cache.ReadFile(r.PathValue("path"))
		if err != nil {
			newError(w, r, err)
			return
		}
		defer reader.Close()

		setContentLength(w, reader)

		if _, err := io.Copy(w, reader); err != nil {
			log.Error(r.URL, err)
		}
	})

	mux.HandleFunc("POST /files", func(w http.ResponseWriter, r *http.Request) {
		missing := r.URL.Query().Has("missing")
		present := r.URL.Query().Has("present")
		if !missing && !present {
			missing = true
			present = true
		}

		request := FindFilesRequest{}
		response := FindFilesResponse{}

		if err := bindJSON(r, &request); err != nil {
			newError(w, r, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
			return
		}

		for _, path := range request.Files {
			info := cache.HasFile(path)

			if present && info != nil {
				response.Present = append(response.Present, path)
			}

			if missing && info == nil {
				response.Missing = append(response.Missing, path)
			}
		}

		writeJSON(w, http.StatusOK, response)
	})

	mux.HandleFunc("PUT /files/{path}", func(w http.ResponseWriter, r *http.Request) {
		writer, err := cache.WriteFile(r.PathValue("path"))
		if err != nil {
			newError(w, r, err)
			return
		}

		if _, err := io.Copy(writer, r.Body); err != nil {
			writer.Discard()
			newError(w, r, err)
			return
		}
		writer.Close()

		writeJSON(w, http.StatusCreated, nil)
	})

	mux.HandleFunc("GET /metrics", func(w http.ResponseWriter, r *http.Request) {
		stats := cache.Statistics()

		metrics := ""
		metrics += fmt.Sprintln("# TYPE jolt_cache_artifacts gauge")
		metrics += fmt.Sprintln("# HELP jolt_cache_artifacts The total number of artifacts currently in the cache (files + objects).")
		metrics += fmt.Sprintf("jolt_cache_artifacts %d\n", stats.Artifacts)

		metrics += fmt.Sprintln("# TYPE jolt_cache_evictions_total counter")
		metrics += fmt.Sprintln("# HELP jolt_cache_evictions_total The total number of evicted artifacts.")
		metrics += fmt.Sprintf("jolt_cache_evictions_total %d\n", stats.Evictions)

		metrics += fmt.Sprintln("# TYPE jolt_cache_hits_total counter")
		metrics += fmt.Sprintln("# HELP jolt_cache_hits_total The total number of cache hits.")
		metrics += fmt.Sprintf("jolt_cache_hits_total %d\n", stats.Hits)

		metrics += fmt.Sprintln("# TYPE jolt_cache_misses_total counter")
		metrics += fmt.Sprintln("# HELP jolt_cache_misses_total The total number of cache misses.")
		metrics += fmt.Sprintf("jolt_cache_misses_total %d\n", stats.Misses)

		metrics += fmt.Sprintln("# TYPE jolt_cache_size_bytes gauge")
		metrics += fmt.Sprintln("# HELP jolt_cache_size_bytes The current size of all artifacts in the cache, in bytes.")
		metrics += fmt.Sprintf("jolt_cache_size_bytes %d\n", stats.Size)

		if service != nil {
			metrics += treeMetrics(service.TreeStatistics())
		}

		w.Header().Set("Content-Type", "text/plain; charset=UTF-8")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(metrics))
	})

	return utils.HttpLogger(mux)
}

// Formats statistics of HasTree requests as metrics.
func treeMetrics(stats TreeStats) string {
	metric := func(name, kind, help string, value any) string {
		return fmt.Sprintf("# TYPE %s %s\n# HELP %s %s\n%s %v\n", name, kind, name, help, name, value)
	}

	metrics := ""
	metrics += metric("jolt_cache_hastree_requests_total", "counter",
		"The total number of HasTree requests, which check that a workspace tree is complete.", stats.Requests)
	metrics += metric("jolt_cache_hastree_seconds_total", "counter",
		"The total time spent serving HasTree requests, in seconds.", stats.Duration.Seconds())
	metrics += metric("jolt_cache_hastree_trees_total", "counter",
		"The total number of trees checked by HasTree requests.", stats.Trees)
	metrics += metric("jolt_cache_hastree_objects_total", "counter",
		"The total number of objects checked by HasTree requests.", stats.Objects)
	metrics += metric("jolt_cache_tree_cache_hits_total", "counter",
		"The total number of trees checked whose parsed content was kept in memory.", stats.CacheHits)
	metrics += metric("jolt_cache_tree_cache_misses_total", "counter",
		"The total number of trees checked that had to be read and parsed.", stats.CacheMisses)
	metrics += metric("jolt_cache_tree_cache_evictions_total", "counter",
		"The total number of parsed trees dropped from memory to make room for others.", stats.CacheEvictions)
	metrics += metric("jolt_cache_tree_cache_trees", "gauge",
		"The number of parsed trees currently kept in memory.", stats.CachedTrees)
	metrics += metric("jolt_cache_tree_cache_size_bytes", "gauge",
		"The approximate memory used by parsed trees kept in memory, in bytes.", stats.CacheSize)
	return metrics
}
