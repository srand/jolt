package worker

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func NewWorkerClient(scheduler string) (protocol.WorkerClient, error) {
	dialOptions := grpc.WithTransportCredentials(insecure.NewCredentials())

	conn, err := grpc.Dial(scheduler, dialOptions)
	if err != nil {
		return nil, err
	}

	return protocol.NewWorkerClient(conn), nil
}
