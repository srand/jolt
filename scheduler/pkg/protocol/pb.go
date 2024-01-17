package protocol

// Generate all protobufs
//go:generate protoc -I../../.. --go_out=../.. --go-grpc_out=../.. jolt/common.proto
//go:generate protoc -I../../.. --go_out=../.. --go-grpc_out=../.. jolt/plugins/remote_execution/administration.proto
//go:generate protoc -I../../.. --go_out=../.. --go-grpc_out=../.. jolt/plugins/remote_execution/scheduler.proto
//go:generate protoc -I../../.. --go_out=../.. --go-grpc_out=../.. jolt/plugins/remote_execution/worker.proto
//go:generate protoc -I../../.. --go_out=../.. --go-grpc_out=../.. scheduler/pkg/logstash/log.proto
