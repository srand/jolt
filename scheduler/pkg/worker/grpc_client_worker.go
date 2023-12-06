package worker

import (
	"errors"
	"net/url"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func NewWorkerClient(workerConfig *WorkerConfig) (protocol.WorkerClient, error) {
	dialOptions := grpc.WithTransportCredentials(insecure.NewCredentials())

	uri, err := url.Parse(workerConfig.SchedulerUri)
	if err != nil {
		return nil, err
	}

	port := uri.Port()
	if port == "" {
		uri.Host += ":9090"
	}

	var grpcUri string
	switch uri.Scheme {
	case "tcp":
		grpcUri = uri.Host

	// These are not yet supported by the Go implementation of gRPC,
	// but are valid in the gRPC c-core implementation.
	// https://github.com/grpc/grpc/blob/master/doc/naming.md#name-syntax
	//
	// case "tcp4":
	// 	grpcUri = "ipv4:" + uri.Host + ":" + port
	//
	// case "tcp6":
	// 	grpcUri = "ipv6:" + uri.Host + ":" + port
	//
	// case "unix":
	// 	grpcUri = fmt.Sprintf("uds://%s", uri.Path)

	default:
		return nil, errors.New("Unsupported protocol: " + uri.Scheme)
	}

	conn, err := grpc.Dial(grpcUri, dialOptions)
	if err != nil {
		return nil, err
	}

	return protocol.NewWorkerClient(conn), nil
}
