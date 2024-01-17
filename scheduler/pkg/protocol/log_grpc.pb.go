// Code generated by protoc-gen-go-grpc. DO NOT EDIT.
// versions:
// - protoc-gen-go-grpc v1.2.0
// - protoc             v3.12.4
// source: scheduler/pkg/logstash/log.proto

package protocol

import (
	context "context"
	grpc "google.golang.org/grpc"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
)

// This is a compile-time assertion to ensure that this generated file
// is compatible with the grpc package it is being compiled against.
// Requires gRPC-Go v1.32.0 or later.
const _ = grpc.SupportPackageIsVersion7

// LogStashClient is the client API for LogStash service.
//
// For semantics around ctx use and closing/ending streaming RPCs, please refer to https://pkg.go.dev/google.golang.org/grpc/?tab=doc#ClientConn.NewStream.
type LogStashClient interface {
	// Read a log file.
	// Log lines are streamed back as they are read from internal storage.
	ReadLog(ctx context.Context, in *ReadLogRequest, opts ...grpc.CallOption) (LogStash_ReadLogClient, error)
}

type logStashClient struct {
	cc grpc.ClientConnInterface
}

func NewLogStashClient(cc grpc.ClientConnInterface) LogStashClient {
	return &logStashClient{cc}
}

func (c *logStashClient) ReadLog(ctx context.Context, in *ReadLogRequest, opts ...grpc.CallOption) (LogStash_ReadLogClient, error) {
	stream, err := c.cc.NewStream(ctx, &LogStash_ServiceDesc.Streams[0], "/LogStash/ReadLog", opts...)
	if err != nil {
		return nil, err
	}
	x := &logStashReadLogClient{stream}
	if err := x.ClientStream.SendMsg(in); err != nil {
		return nil, err
	}
	if err := x.ClientStream.CloseSend(); err != nil {
		return nil, err
	}
	return x, nil
}

type LogStash_ReadLogClient interface {
	Recv() (*ReadLogResponse, error)
	grpc.ClientStream
}

type logStashReadLogClient struct {
	grpc.ClientStream
}

func (x *logStashReadLogClient) Recv() (*ReadLogResponse, error) {
	m := new(ReadLogResponse)
	if err := x.ClientStream.RecvMsg(m); err != nil {
		return nil, err
	}
	return m, nil
}

// LogStashServer is the server API for LogStash service.
// All implementations must embed UnimplementedLogStashServer
// for forward compatibility
type LogStashServer interface {
	// Read a log file.
	// Log lines are streamed back as they are read from internal storage.
	ReadLog(*ReadLogRequest, LogStash_ReadLogServer) error
	mustEmbedUnimplementedLogStashServer()
}

// UnimplementedLogStashServer must be embedded to have forward compatible implementations.
type UnimplementedLogStashServer struct {
}

func (UnimplementedLogStashServer) ReadLog(*ReadLogRequest, LogStash_ReadLogServer) error {
	return status.Errorf(codes.Unimplemented, "method ReadLog not implemented")
}
func (UnimplementedLogStashServer) mustEmbedUnimplementedLogStashServer() {}

// UnsafeLogStashServer may be embedded to opt out of forward compatibility for this service.
// Use of this interface is not recommended, as added methods to LogStashServer will
// result in compilation errors.
type UnsafeLogStashServer interface {
	mustEmbedUnimplementedLogStashServer()
}

func RegisterLogStashServer(s grpc.ServiceRegistrar, srv LogStashServer) {
	s.RegisterService(&LogStash_ServiceDesc, srv)
}

func _LogStash_ReadLog_Handler(srv interface{}, stream grpc.ServerStream) error {
	m := new(ReadLogRequest)
	if err := stream.RecvMsg(m); err != nil {
		return err
	}
	return srv.(LogStashServer).ReadLog(m, &logStashReadLogServer{stream})
}

type LogStash_ReadLogServer interface {
	Send(*ReadLogResponse) error
	grpc.ServerStream
}

type logStashReadLogServer struct {
	grpc.ServerStream
}

func (x *logStashReadLogServer) Send(m *ReadLogResponse) error {
	return x.ServerStream.SendMsg(m)
}

// LogStash_ServiceDesc is the grpc.ServiceDesc for LogStash service.
// It's only intended for direct use with grpc.RegisterService,
// and not to be introspected or modified (even as a copy)
var LogStash_ServiceDesc = grpc.ServiceDesc{
	ServiceName: "LogStash",
	HandlerType: (*LogStashServer)(nil),
	Methods:     []grpc.MethodDesc{},
	Streams: []grpc.StreamDesc{
		{
			StreamName:    "ReadLog",
			Handler:       _LogStash_ReadLog_Handler,
			ServerStreams: true,
		},
	},
	Metadata: "scheduler/pkg/logstash/log.proto",
}
