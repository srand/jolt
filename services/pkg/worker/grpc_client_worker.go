package worker

import (
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func NewWorkerClient(workerConfig *WorkerConfig) (protocol.WorkerClient, error) {
	dialOptions := grpc.WithTransportCredentials(insecure.NewCredentials())

	grpcUri, err := utils.ParseGrpcUrl(workerConfig.SchedulerUri)
	if err != nil {
		return nil, err
	}

	conn, err := grpc.Dial(grpcUri, dialOptions)
	if err != nil {
		return nil, err
	}

	return protocol.NewWorkerClient(conn), nil
}
