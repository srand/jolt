// Package validate checks incoming gRPC messages against the protovalidate
// rules declared in their protobuf definitions.
package validate

import (
	"context"
	"errors"

	"buf.build/go/protovalidate"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

var validator = func() protovalidate.Validator {
	validator, err := protovalidate.New()
	if err != nil {
		panic(err)
	}
	return validator
}()

// A server stream that validates the messages it receives.
type validatingStream struct {
	grpc.ServerStream
}

func (s validatingStream) RecvMsg(m any) error {
	if err := s.ServerStream.RecvMsg(m); err != nil {
		return err
	}
	return validate(m)
}

// Returns an InvalidArgument error if the message breaks its rules.
func validate(m any) error {
	message, ok := m.(proto.Message)
	if !ok {
		return nil
	}

	err := validator.Validate(message)
	if err == nil {
		return nil
	}

	var verr *protovalidate.ValidationError
	if !errors.As(err, &verr) {
		return status.Errorf(codes.Internal, "failed to validate message: %v", err)
	}

	st := status.New(codes.InvalidArgument, verr.Error())
	if detailed, err := st.WithDetails(verr.ToProto()); err == nil {
		st = detailed
	}
	return st.Err()
}

// ServerOptions returns gRPC server options that reject requests and stream
// messages that break their rules with InvalidArgument. Add them after the
// authentication options so that unauthenticated calls are rejected first.
func ServerOptions() []grpc.ServerOption {
	return []grpc.ServerOption{
		grpc.ChainUnaryInterceptor(func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
			if err := validate(req); err != nil {
				return nil, err
			}
			return handler(ctx, req)
		}),
		grpc.ChainStreamInterceptor(func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
			return handler(srv, validatingStream{ServerStream: ss})
		}),
	}
}
