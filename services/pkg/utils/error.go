package utils

import (
	"fmt"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

var (
	ErrBadRequest       = fmt.Errorf("Bad request")
	ErrNoEligibleWorker = fmt.Errorf("No eligible worker available")
	ErrNoTask           = fmt.Errorf("No tasks available")
	ErrNotFound         = fmt.Errorf("Not found")
	ErrParse            = fmt.Errorf("Parse error")
	ErrTerminalBuild    = fmt.Errorf("Build is terminal")
)

type DetailedError interface {
	error
	Details() string
}

// Convert errors to errors with grpc status codes
func GrpcError(err error) error {
	switch err {
	case ErrNotFound:
		return status.Errorf(codes.NotFound, err.Error())
	case ErrNoEligibleWorker:
		return status.Errorf(codes.Unavailable, err.Error())
	case ErrNoTask:
		return status.Errorf(codes.Unavailable, err.Error())
	case ErrTerminalBuild:
		return status.Errorf(codes.FailedPrecondition, err.Error())
	}
	return err
}
