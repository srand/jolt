package utils

import (
	"fmt"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

var (
	NoEligibleWorkerError = fmt.Errorf("No eligible worker available")
	NoTaskError           = fmt.Errorf("No tasks available")
	NotFoundError         = fmt.Errorf("Not found")
)

type DetailedError interface {
	error
	Details() string
}

// Convert errors to errors with grpc status codes
func GrpcError(err error) error {
	switch err {
	case NotFoundError:
		return status.Errorf(codes.NotFound, err.Error())
	case NoEligibleWorkerError:
		return status.Errorf(codes.Unavailable, err.Error())
	case NoTaskError:
		return status.Errorf(codes.Unavailable, err.Error())
	}
	return err
}
