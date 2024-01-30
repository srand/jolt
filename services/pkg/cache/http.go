package cache

import (
	"errors"
	"fmt"
	"io"
	"net/http"

	"github.com/labstack/echo/v4"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type Error struct {
	Message string `json:"message"`
}

func newError(c echo.Context, err error) error {
	if errors.Is(err, utils.ErrNotFound) {
		return c.JSON(http.StatusNotFound, &Error{Message: err.Error()})
	}

	if errors.Is(err, utils.ErrBadRequest) {
		return c.JSON(http.StatusBadRequest, &Error{Message: err.Error()})
	}

	log.Error(c.Request().URL, err)
	return c.JSON(http.StatusInternalServerError, &Error{Message: err.Error()})
}

type FindBlobsRequest struct {
	Blobs []utils.Digest
}

type FindBlobsResponse struct {
	Blobs []utils.Digest
}

func NewHttpHandler(cache Cache) http.Handler {
	r := echo.New()
	r.HideBanner = true
	r.Use(utils.HttpLogger)

	r.HEAD("/objects/:digest", func(c echo.Context) error {
		digest, err := utils.ParseDigest(c.Param("digest"))
		if err != nil {
			return newError(c, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
		}

		if info := cache.HasObject(digest); info != nil {
			c.Response().Header().Set(echo.HeaderContentLength, fmt.Sprint(info.Size()))
			return c.JSON(http.StatusOK, nil)
		}

		return newError(c, utils.ErrNotFound)
	})

	r.GET("/objects/:digest", func(c echo.Context) error {
		digest, err := utils.ParseDigest(c.Param("digest"))
		if err != nil {
			return newError(c, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
		}

		reader, err := cache.ReadObject(digest)
		if err != nil {
			return newError(c, err)
		}
		defer reader.Close()

		if _, err := io.Copy(c.Response().Writer, reader); err != nil {
			return newError(c, err)
		}

		return nil
	})

	r.POST("/objects", func(c echo.Context) error {
		present := c.QueryParam("present") != "false"
		request := FindBlobsRequest{}
		response := FindBlobsResponse{}

		if err := c.Bind(&request); err != nil {
			return newError(c, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
		}

		for _, digest := range request.Blobs {
			info := cache.HasObject(digest)

			if present && info != nil {
				response.Blobs = append(response.Blobs, digest)
			}

			if !present && info == nil {
				response.Blobs = append(response.Blobs, digest)
			}
		}

		return c.JSON(http.StatusOK, response)
	})

	r.PUT("/objects/:digest", func(c echo.Context) error {
		digest, err := utils.ParseDigest(c.Param("digest"))
		if err != nil {
			return newError(c, fmt.Errorf("%v: %v", utils.ErrBadRequest, err))
		}

		writer, err := cache.WriteObject(digest)
		if err != nil {
			return newError(c, err)
		}
		defer writer.Close()

		if _, err := io.Copy(writer, c.Request().Body); err != nil {
			return newError(c, err)
		}

		return c.JSON(http.StatusCreated, nil)
	})

	r.HEAD("/files/:path", func(c echo.Context) error {
		if info := cache.HasFile(c.Param("path")); info != nil {
			c.Response().Header().Set(echo.HeaderContentLength, fmt.Sprint(info.Size()))
			return c.JSON(http.StatusOK, nil)
		}

		return newError(c, utils.ErrNotFound)
	})

	r.GET("/files/:path", func(c echo.Context) error {
		reader, err := cache.ReadFile(c.Param("path"))
		if err != nil {
			return newError(c, err)
		}
		defer reader.Close()

		if _, err := io.Copy(c.Response().Writer, reader); err != nil {
			return newError(c, err)
		}

		return nil
	})

	r.PUT("/files/:path", func(c echo.Context) error {
		writer, err := cache.WriteFile(c.Param("path"))
		if err != nil {
			return newError(c, err)
		}
		defer writer.Close()

		if _, err := io.Copy(writer, c.Request().Body); err != nil {
			return newError(c, err)
		}

		return c.JSON(http.StatusCreated, nil)
	})

	r.GET("/metrics", func(c echo.Context) error {
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

		return c.String(http.StatusOK, metrics)
	})

	return r
}
