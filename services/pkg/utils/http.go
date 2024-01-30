package utils

import (
	"github.com/labstack/echo/v4"
	"github.com/srand/jolt/scheduler/pkg/log"
)

func HttpLogger(next echo.HandlerFunc) echo.HandlerFunc {
	return func(c echo.Context) error {
		err := next(c)
		log.Tracef("%4s %s %v", c.Request().Method, c.Request().URL, c.Response().Status)
		return err
	}
}
