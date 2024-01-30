package logstash

import (
	"bufio"
	"fmt"
	"io"
	"net/http"

	echo "github.com/labstack/echo/v4"
)

func NewHttpHandler(stash LogStash, r *echo.Echo) http.Handler {
	r.GET("/logs/:id", func(c echo.Context) error {
		reader, err := stash.Read(c.Param("id"))
		if err != nil {
			return c.String(http.StatusNotFound, err.Error())
		}
		defer reader.Close()

		c.Response().Header().Set(echo.HeaderContentType, echo.MIMETextPlain)
		c.Response().WriteHeader(http.StatusOK)
		writer := bufio.NewWriter(c.Response())

		for {
			record, err := reader.ReadLine()
			if err == io.EOF {
				return nil
			}

			if err != nil {
				return c.String(http.StatusInternalServerError, err.Error())
			}

			ts := record.Time.AsTime().Local()
			line := fmt.Sprintf(
				"%s.%06d [%7s] %s\n",
				ts.Format("2006-01-02 15:04:05"),
				ts.Nanosecond()/1000,
				record.Level.String(),
				record.Message)

			if _, err := writer.WriteString(line); err != nil {
				return c.String(http.StatusInternalServerError, err.Error())
			}

			writer.Flush()
		}
	})

	return r
}
