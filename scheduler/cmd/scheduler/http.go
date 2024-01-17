package main

import (
	"bufio"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	echo "github.com/labstack/echo/v4"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/logstash"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

func HttpLogger(next echo.HandlerFunc) echo.HandlerFunc {
	return func(c echo.Context) error {
		err := next(c)
		log.Trace("HTTP", c.Request().Method, c.Response().Status, c.Request().URL, err)
		return err
	}
}

func serveHttp(stash logstash.LogStash, uri string) {
	host, err := utils.ParseHttpUrl(uri)
	if err != nil {
		log.Fatal(err)
	}

	r := echo.New()
	r.HideBanner = true
	r.Use(HttpLogger)

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

			line := fmt.Sprintf("%s %7s - %s\n", record.Time.AsTime().Local().Format(time.RFC3339), strings.ToLower(record.Level.String()), record.Message)

			if _, err := writer.WriteString(line); err != nil {
				return c.String(http.StatusInternalServerError, err.Error())
			}

			writer.Flush()
		}
	})

	if err := r.Start(host); err != nil {
		log.Fatal(err)
	}
}
