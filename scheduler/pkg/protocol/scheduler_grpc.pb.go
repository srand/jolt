// Code generated by protoc-gen-go-grpc. DO NOT EDIT.
// versions:
// - protoc-gen-go-grpc v1.2.0
// - protoc             v3.12.4
// source: jolt/plugins/remote_execution/scheduler.proto

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

// SchedulerClient is the client API for Scheduler service.
//
// For semantics around ctx use and closing/ending streaming RPCs, please refer to https://pkg.go.dev/google.golang.org/grpc/?tab=doc#ClientConn.NewStream.
type SchedulerClient interface {
	// Create a new build in the scheduler.
	// The build is not started until tasks are scheduled.
	ScheduleBuild(ctx context.Context, in *BuildRequest, opts ...grpc.CallOption) (*BuildResponse, error)
	// Cancel a build.
	CancelBuild(ctx context.Context, in *CancelBuildRequest, opts ...grpc.CallOption) (*CancelBuildResponse, error)
	// Schedule a task to be executed.
	// The scheduler will assign the task to a free worker
	// and updates will be sent back once the task is running.
	ScheduleTask(ctx context.Context, in *TaskRequest, opts ...grpc.CallOption) (Scheduler_ScheduleTaskClient, error)
}

type schedulerClient struct {
	cc grpc.ClientConnInterface
}

func NewSchedulerClient(cc grpc.ClientConnInterface) SchedulerClient {
	return &schedulerClient{cc}
}

func (c *schedulerClient) ScheduleBuild(ctx context.Context, in *BuildRequest, opts ...grpc.CallOption) (*BuildResponse, error) {
	out := new(BuildResponse)
	err := c.cc.Invoke(ctx, "/Scheduler/ScheduleBuild", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *schedulerClient) CancelBuild(ctx context.Context, in *CancelBuildRequest, opts ...grpc.CallOption) (*CancelBuildResponse, error) {
	out := new(CancelBuildResponse)
	err := c.cc.Invoke(ctx, "/Scheduler/CancelBuild", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *schedulerClient) ScheduleTask(ctx context.Context, in *TaskRequest, opts ...grpc.CallOption) (Scheduler_ScheduleTaskClient, error) {
	stream, err := c.cc.NewStream(ctx, &Scheduler_ServiceDesc.Streams[0], "/Scheduler/ScheduleTask", opts...)
	if err != nil {
		return nil, err
	}
	x := &schedulerScheduleTaskClient{stream}
	if err := x.ClientStream.SendMsg(in); err != nil {
		return nil, err
	}
	if err := x.ClientStream.CloseSend(); err != nil {
		return nil, err
	}
	return x, nil
}

type Scheduler_ScheduleTaskClient interface {
	Recv() (*TaskUpdate, error)
	grpc.ClientStream
}

type schedulerScheduleTaskClient struct {
	grpc.ClientStream
}

func (x *schedulerScheduleTaskClient) Recv() (*TaskUpdate, error) {
	m := new(TaskUpdate)
	if err := x.ClientStream.RecvMsg(m); err != nil {
		return nil, err
	}
	return m, nil
}

// SchedulerServer is the server API for Scheduler service.
// All implementations must embed UnimplementedSchedulerServer
// for forward compatibility
type SchedulerServer interface {
	// Create a new build in the scheduler.
	// The build is not started until tasks are scheduled.
	ScheduleBuild(context.Context, *BuildRequest) (*BuildResponse, error)
	// Cancel a build.
	CancelBuild(context.Context, *CancelBuildRequest) (*CancelBuildResponse, error)
	// Schedule a task to be executed.
	// The scheduler will assign the task to a free worker
	// and updates will be sent back once the task is running.
	ScheduleTask(*TaskRequest, Scheduler_ScheduleTaskServer) error
	mustEmbedUnimplementedSchedulerServer()
}

// UnimplementedSchedulerServer must be embedded to have forward compatible implementations.
type UnimplementedSchedulerServer struct {
}

func (UnimplementedSchedulerServer) ScheduleBuild(context.Context, *BuildRequest) (*BuildResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ScheduleBuild not implemented")
}
func (UnimplementedSchedulerServer) CancelBuild(context.Context, *CancelBuildRequest) (*CancelBuildResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method CancelBuild not implemented")
}
func (UnimplementedSchedulerServer) ScheduleTask(*TaskRequest, Scheduler_ScheduleTaskServer) error {
	return status.Errorf(codes.Unimplemented, "method ScheduleTask not implemented")
}
func (UnimplementedSchedulerServer) mustEmbedUnimplementedSchedulerServer() {}

// UnsafeSchedulerServer may be embedded to opt out of forward compatibility for this service.
// Use of this interface is not recommended, as added methods to SchedulerServer will
// result in compilation errors.
type UnsafeSchedulerServer interface {
	mustEmbedUnimplementedSchedulerServer()
}

func RegisterSchedulerServer(s grpc.ServiceRegistrar, srv SchedulerServer) {
	s.RegisterService(&Scheduler_ServiceDesc, srv)
}

func _Scheduler_ScheduleBuild_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(BuildRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(SchedulerServer).ScheduleBuild(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/Scheduler/ScheduleBuild",
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(SchedulerServer).ScheduleBuild(ctx, req.(*BuildRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _Scheduler_CancelBuild_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(CancelBuildRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(SchedulerServer).CancelBuild(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: "/Scheduler/CancelBuild",
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(SchedulerServer).CancelBuild(ctx, req.(*CancelBuildRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _Scheduler_ScheduleTask_Handler(srv interface{}, stream grpc.ServerStream) error {
	m := new(TaskRequest)
	if err := stream.RecvMsg(m); err != nil {
		return err
	}
	return srv.(SchedulerServer).ScheduleTask(m, &schedulerScheduleTaskServer{stream})
}

type Scheduler_ScheduleTaskServer interface {
	Send(*TaskUpdate) error
	grpc.ServerStream
}

type schedulerScheduleTaskServer struct {
	grpc.ServerStream
}

func (x *schedulerScheduleTaskServer) Send(m *TaskUpdate) error {
	return x.ServerStream.SendMsg(m)
}

// Scheduler_ServiceDesc is the grpc.ServiceDesc for Scheduler service.
// It's only intended for direct use with grpc.RegisterService,
// and not to be introspected or modified (even as a copy)
var Scheduler_ServiceDesc = grpc.ServiceDesc{
	ServiceName: "Scheduler",
	HandlerType: (*SchedulerServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "ScheduleBuild",
			Handler:    _Scheduler_ScheduleBuild_Handler,
		},
		{
			MethodName: "CancelBuild",
			Handler:    _Scheduler_CancelBuild_Handler,
		},
	},
	Streams: []grpc.StreamDesc{
		{
			StreamName:    "ScheduleTask",
			Handler:       _Scheduler_ScheduleTask_Handler,
			ServerStreams: true,
		},
	},
	Metadata: "jolt/plugins/remote_execution/scheduler.proto",
}