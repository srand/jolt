// Code generated by protoc-gen-go-grpc. DO NOT EDIT.
// versions:
// - protoc-gen-go-grpc v1.3.0
// - protoc             v4.24.4
// source: jolt/plugins/remote_execution/administration.proto

package protocol

import (
	context "context"
	grpc "google.golang.org/grpc"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
	emptypb "google.golang.org/protobuf/types/known/emptypb"
)

// This is a compile-time assertion to ensure that this generated file
// is compatible with the grpc package it is being compiled against.
// Requires gRPC-Go v1.32.0 or later.
const _ = grpc.SupportPackageIsVersion7

const (
	Administration_CancelBuild_FullMethodName = "/Administration/CancelBuild"
	Administration_ListBuilds_FullMethodName  = "/Administration/ListBuilds"
	Administration_ListWorkers_FullMethodName = "/Administration/ListWorkers"
	Administration_Reschedule_FullMethodName  = "/Administration/Reschedule"
)

// AdministrationClient is the client API for Administration service.
//
// For semantics around ctx use and closing/ending streaming RPCs, please refer to https://pkg.go.dev/google.golang.org/grpc/?tab=doc#ClientConn.NewStream.
type AdministrationClient interface {
	CancelBuild(ctx context.Context, in *CancelBuildRequest, opts ...grpc.CallOption) (*CancelBuildResponse, error)
	ListBuilds(ctx context.Context, in *ListBuildsRequest, opts ...grpc.CallOption) (*ListBuildsResponse, error)
	ListWorkers(ctx context.Context, in *ListWorkersRequest, opts ...grpc.CallOption) (*ListWorkersResponse, error)
	Reschedule(ctx context.Context, in *emptypb.Empty, opts ...grpc.CallOption) (*emptypb.Empty, error)
}

type administrationClient struct {
	cc grpc.ClientConnInterface
}

func NewAdministrationClient(cc grpc.ClientConnInterface) AdministrationClient {
	return &administrationClient{cc}
}

func (c *administrationClient) CancelBuild(ctx context.Context, in *CancelBuildRequest, opts ...grpc.CallOption) (*CancelBuildResponse, error) {
	out := new(CancelBuildResponse)
	err := c.cc.Invoke(ctx, Administration_CancelBuild_FullMethodName, in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *administrationClient) ListBuilds(ctx context.Context, in *ListBuildsRequest, opts ...grpc.CallOption) (*ListBuildsResponse, error) {
	out := new(ListBuildsResponse)
	err := c.cc.Invoke(ctx, Administration_ListBuilds_FullMethodName, in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *administrationClient) ListWorkers(ctx context.Context, in *ListWorkersRequest, opts ...grpc.CallOption) (*ListWorkersResponse, error) {
	out := new(ListWorkersResponse)
	err := c.cc.Invoke(ctx, Administration_ListWorkers_FullMethodName, in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (c *administrationClient) Reschedule(ctx context.Context, in *emptypb.Empty, opts ...grpc.CallOption) (*emptypb.Empty, error) {
	out := new(emptypb.Empty)
	err := c.cc.Invoke(ctx, Administration_Reschedule_FullMethodName, in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}

// AdministrationServer is the server API for Administration service.
// All implementations must embed UnimplementedAdministrationServer
// for forward compatibility
type AdministrationServer interface {
	CancelBuild(context.Context, *CancelBuildRequest) (*CancelBuildResponse, error)
	ListBuilds(context.Context, *ListBuildsRequest) (*ListBuildsResponse, error)
	ListWorkers(context.Context, *ListWorkersRequest) (*ListWorkersResponse, error)
	Reschedule(context.Context, *emptypb.Empty) (*emptypb.Empty, error)
	mustEmbedUnimplementedAdministrationServer()
}

// UnimplementedAdministrationServer must be embedded to have forward compatible implementations.
type UnimplementedAdministrationServer struct {
}

func (UnimplementedAdministrationServer) CancelBuild(context.Context, *CancelBuildRequest) (*CancelBuildResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method CancelBuild not implemented")
}
func (UnimplementedAdministrationServer) ListBuilds(context.Context, *ListBuildsRequest) (*ListBuildsResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ListBuilds not implemented")
}
func (UnimplementedAdministrationServer) ListWorkers(context.Context, *ListWorkersRequest) (*ListWorkersResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method ListWorkers not implemented")
}
func (UnimplementedAdministrationServer) Reschedule(context.Context, *emptypb.Empty) (*emptypb.Empty, error) {
	return nil, status.Errorf(codes.Unimplemented, "method Reschedule not implemented")
}
func (UnimplementedAdministrationServer) mustEmbedUnimplementedAdministrationServer() {}

// UnsafeAdministrationServer may be embedded to opt out of forward compatibility for this service.
// Use of this interface is not recommended, as added methods to AdministrationServer will
// result in compilation errors.
type UnsafeAdministrationServer interface {
	mustEmbedUnimplementedAdministrationServer()
}

func RegisterAdministrationServer(s grpc.ServiceRegistrar, srv AdministrationServer) {
	s.RegisterService(&Administration_ServiceDesc, srv)
}

func _Administration_CancelBuild_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(CancelBuildRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(AdministrationServer).CancelBuild(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: Administration_CancelBuild_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(AdministrationServer).CancelBuild(ctx, req.(*CancelBuildRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _Administration_ListBuilds_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ListBuildsRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(AdministrationServer).ListBuilds(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: Administration_ListBuilds_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(AdministrationServer).ListBuilds(ctx, req.(*ListBuildsRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _Administration_ListWorkers_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(ListWorkersRequest)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(AdministrationServer).ListWorkers(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: Administration_ListWorkers_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(AdministrationServer).ListWorkers(ctx, req.(*ListWorkersRequest))
	}
	return interceptor(ctx, in, info, handler)
}

func _Administration_Reschedule_Handler(srv interface{}, ctx context.Context, dec func(interface{}) error, interceptor grpc.UnaryServerInterceptor) (interface{}, error) {
	in := new(emptypb.Empty)
	if err := dec(in); err != nil {
		return nil, err
	}
	if interceptor == nil {
		return srv.(AdministrationServer).Reschedule(ctx, in)
	}
	info := &grpc.UnaryServerInfo{
		Server:     srv,
		FullMethod: Administration_Reschedule_FullMethodName,
	}
	handler := func(ctx context.Context, req interface{}) (interface{}, error) {
		return srv.(AdministrationServer).Reschedule(ctx, req.(*emptypb.Empty))
	}
	return interceptor(ctx, in, info, handler)
}

// Administration_ServiceDesc is the grpc.ServiceDesc for Administration service.
// It's only intended for direct use with grpc.RegisterService,
// and not to be introspected or modified (even as a copy)
var Administration_ServiceDesc = grpc.ServiceDesc{
	ServiceName: "Administration",
	HandlerType: (*AdministrationServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "CancelBuild",
			Handler:    _Administration_CancelBuild_Handler,
		},
		{
			MethodName: "ListBuilds",
			Handler:    _Administration_ListBuilds_Handler,
		},
		{
			MethodName: "ListWorkers",
			Handler:    _Administration_ListWorkers_Handler,
		},
		{
			MethodName: "Reschedule",
			Handler:    _Administration_Reschedule_Handler,
		},
	},
	Streams:  []grpc.StreamDesc{},
	Metadata: "jolt/plugins/remote_execution/administration.proto",
}
