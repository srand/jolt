package logstash

import (
	"fmt"
	"io"
	"net/http"

	echo "github.com/labstack/echo/v4"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

func NewHttpHandler(stash LogStash, r *echo.Echo) http.Handler {
	r.GET("/logs/:id", func(c echo.Context) error {
		var reader LogReader
		var err error

		// Following keeps the response open while the task is still writing.
		if c.QueryParam("follow") == "1" {
			reader, err = stash.Follow(c.Request().Context(), c.Param("id"))
		} else {
			reader, err = stash.Read(c.Param("id"))
		}
		if err != nil {
			return c.String(http.StatusNotFound, err.Error())
		}
		defer reader.Close()

		c.Response().Header().Set(echo.HeaderContentType, echo.MIMETextPlain)
		c.Response().WriteHeader(http.StatusOK)

		for {
			record, err := reader.ReadLine()
			if err == io.EOF {
				return nil
			}

			if err != nil {
				// The status is already sent, so there is nowhere to report
				// this but the log. Debug, not Error: the common cause is a
				// worker dying mid-record (io.ErrUnexpectedEOF), which is
				// routine and already visible via the task's own status.
				log.Debugf("read - log - id: %s - error: %v", c.Param("id"), err)
				return nil
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

			if _, err := c.Response().Write([]byte(line)); err != nil {
				return nil
			}

			// Push the line out now. A bufio.Writer would only move it into
			// net/http's own buffer, where it would wait for ~4KB of company.
			c.Response().Flush()
		}
	})

	return r
}
