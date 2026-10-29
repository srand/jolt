package worker

import (
	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"google.golang.org/grpc"
)

func NewWorkerClient(workerConfig *WorkerConfig) (protocol.WorkerClient, error) {
	target, dialOptions, err := auth.DialOptions(workerConfig.SchedulerGrpcUri, auth.ClientOptions{
		CACert:             workerConfig.CACert,
		Token:              workerConfig.SchedulerToken,
		AllowInsecureToken: workerConfig.AllowInsecureToken,
	})
	if err != nil {
		return nil, err
	}

	dialOptions = append(dialOptions, workerConfig.Grpc.ToDialOptions()...)

	conn, err := grpc.Dial(target, dialOptions...)
	if err != nil {
		return nil, err
	}

	return protocol.NewWorkerClient(conn), nil
}
