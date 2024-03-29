// Code generated by protoc-gen-go. DO NOT EDIT.
// versions:
// 	protoc-gen-go v1.31.0
// 	protoc        v4.24.4
// source: jolt/plugins/remote_execution/administration.proto

package protocol

import (
	protoreflect "google.golang.org/protobuf/reflect/protoreflect"
	protoimpl "google.golang.org/protobuf/runtime/protoimpl"
	emptypb "google.golang.org/protobuf/types/known/emptypb"
	reflect "reflect"
	sync "sync"
)

const (
	// Verify that this generated code is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(20 - protoimpl.MinVersion)
	// Verify that runtime/protoimpl is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(protoimpl.MaxVersion - 20)
)

type ListBuildsRequest struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields
}

func (x *ListBuildsRequest) Reset() {
	*x = ListBuildsRequest{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[0]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ListBuildsRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListBuildsRequest) ProtoMessage() {}

func (x *ListBuildsRequest) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[0]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ListBuildsRequest.ProtoReflect.Descriptor instead.
func (*ListBuildsRequest) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_administration_proto_rawDescGZIP(), []int{0}
}

type ListBuildsResponse struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	Builds []*ListBuildsResponse_Build `protobuf:"bytes,1,rep,name=builds,proto3" json:"builds,omitempty"`
}

func (x *ListBuildsResponse) Reset() {
	*x = ListBuildsResponse{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[1]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ListBuildsResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListBuildsResponse) ProtoMessage() {}

func (x *ListBuildsResponse) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[1]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ListBuildsResponse.ProtoReflect.Descriptor instead.
func (*ListBuildsResponse) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_administration_proto_rawDescGZIP(), []int{1}
}

func (x *ListBuildsResponse) GetBuilds() []*ListBuildsResponse_Build {
	if x != nil {
		return x.Builds
	}
	return nil
}

type ListWorkersRequest struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields
}

func (x *ListWorkersRequest) Reset() {
	*x = ListWorkersRequest{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[2]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ListWorkersRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListWorkersRequest) ProtoMessage() {}

func (x *ListWorkersRequest) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[2]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ListWorkersRequest.ProtoReflect.Descriptor instead.
func (*ListWorkersRequest) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_administration_proto_rawDescGZIP(), []int{2}
}

type ListWorkersResponse struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields
}

func (x *ListWorkersResponse) Reset() {
	*x = ListWorkersResponse{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[3]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ListWorkersResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListWorkersResponse) ProtoMessage() {}

func (x *ListWorkersResponse) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[3]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ListWorkersResponse.ProtoReflect.Descriptor instead.
func (*ListWorkersResponse) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_administration_proto_rawDescGZIP(), []int{3}
}

type ListBuildsResponse_Build struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	Id string `protobuf:"bytes,1,opt,name=id,proto3" json:"id,omitempty"`
}

func (x *ListBuildsResponse_Build) Reset() {
	*x = ListBuildsResponse_Build{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[4]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ListBuildsResponse_Build) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ListBuildsResponse_Build) ProtoMessage() {}

func (x *ListBuildsResponse_Build) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_administration_proto_msgTypes[4]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ListBuildsResponse_Build.ProtoReflect.Descriptor instead.
func (*ListBuildsResponse_Build) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_administration_proto_rawDescGZIP(), []int{1, 0}
}

func (x *ListBuildsResponse_Build) GetId() string {
	if x != nil {
		return x.Id
	}
	return ""
}

var File_jolt_plugins_remote_execution_administration_proto protoreflect.FileDescriptor

var file_jolt_plugins_remote_execution_administration_proto_rawDesc = []byte{
	0x0a, 0x32, 0x6a, 0x6f, 0x6c, 0x74, 0x2f, 0x70, 0x6c, 0x75, 0x67, 0x69, 0x6e, 0x73, 0x2f, 0x72,
	0x65, 0x6d, 0x6f, 0x74, 0x65, 0x5f, 0x65, 0x78, 0x65, 0x63, 0x75, 0x74, 0x69, 0x6f, 0x6e, 0x2f,
	0x61, 0x64, 0x6d, 0x69, 0x6e, 0x69, 0x73, 0x74, 0x72, 0x61, 0x74, 0x69, 0x6f, 0x6e, 0x2e, 0x70,
	0x72, 0x6f, 0x74, 0x6f, 0x1a, 0x1b, 0x67, 0x6f, 0x6f, 0x67, 0x6c, 0x65, 0x2f, 0x70, 0x72, 0x6f,
	0x74, 0x6f, 0x62, 0x75, 0x66, 0x2f, 0x65, 0x6d, 0x70, 0x74, 0x79, 0x2e, 0x70, 0x72, 0x6f, 0x74,
	0x6f, 0x1a, 0x2d, 0x6a, 0x6f, 0x6c, 0x74, 0x2f, 0x70, 0x6c, 0x75, 0x67, 0x69, 0x6e, 0x73, 0x2f,
	0x72, 0x65, 0x6d, 0x6f, 0x74, 0x65, 0x5f, 0x65, 0x78, 0x65, 0x63, 0x75, 0x74, 0x69, 0x6f, 0x6e,
	0x2f, 0x73, 0x63, 0x68, 0x65, 0x64, 0x75, 0x6c, 0x65, 0x72, 0x2e, 0x70, 0x72, 0x6f, 0x74, 0x6f,
	0x22, 0x13, 0x0a, 0x11, 0x4c, 0x69, 0x73, 0x74, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x73, 0x52, 0x65,
	0x71, 0x75, 0x65, 0x73, 0x74, 0x22, 0x60, 0x0a, 0x12, 0x4c, 0x69, 0x73, 0x74, 0x42, 0x75, 0x69,
	0x6c, 0x64, 0x73, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73, 0x65, 0x12, 0x31, 0x0a, 0x06, 0x62,
	0x75, 0x69, 0x6c, 0x64, 0x73, 0x18, 0x01, 0x20, 0x03, 0x28, 0x0b, 0x32, 0x19, 0x2e, 0x4c, 0x69,
	0x73, 0x74, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x73, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73, 0x65,
	0x2e, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x52, 0x06, 0x62, 0x75, 0x69, 0x6c, 0x64, 0x73, 0x1a, 0x17,
	0x0a, 0x05, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x12, 0x0e, 0x0a, 0x02, 0x69, 0x64, 0x18, 0x01, 0x20,
	0x01, 0x28, 0x09, 0x52, 0x02, 0x69, 0x64, 0x22, 0x14, 0x0a, 0x12, 0x4c, 0x69, 0x73, 0x74, 0x57,
	0x6f, 0x72, 0x6b, 0x65, 0x72, 0x73, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x22, 0x15, 0x0a,
	0x13, 0x4c, 0x69, 0x73, 0x74, 0x57, 0x6f, 0x72, 0x6b, 0x65, 0x72, 0x73, 0x52, 0x65, 0x73, 0x70,
	0x6f, 0x6e, 0x73, 0x65, 0x32, 0xf9, 0x01, 0x0a, 0x0e, 0x41, 0x64, 0x6d, 0x69, 0x6e, 0x69, 0x73,
	0x74, 0x72, 0x61, 0x74, 0x69, 0x6f, 0x6e, 0x12, 0x38, 0x0a, 0x0b, 0x43, 0x61, 0x6e, 0x63, 0x65,
	0x6c, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x12, 0x13, 0x2e, 0x43, 0x61, 0x6e, 0x63, 0x65, 0x6c, 0x42,
	0x75, 0x69, 0x6c, 0x64, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x1a, 0x14, 0x2e, 0x43, 0x61,
	0x6e, 0x63, 0x65, 0x6c, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73,
	0x65, 0x12, 0x35, 0x0a, 0x0a, 0x4c, 0x69, 0x73, 0x74, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x73, 0x12,
	0x12, 0x2e, 0x4c, 0x69, 0x73, 0x74, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x73, 0x52, 0x65, 0x71, 0x75,
	0x65, 0x73, 0x74, 0x1a, 0x13, 0x2e, 0x4c, 0x69, 0x73, 0x74, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x73,
	0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73, 0x65, 0x12, 0x38, 0x0a, 0x0b, 0x4c, 0x69, 0x73, 0x74,
	0x57, 0x6f, 0x72, 0x6b, 0x65, 0x72, 0x73, 0x12, 0x13, 0x2e, 0x4c, 0x69, 0x73, 0x74, 0x57, 0x6f,
	0x72, 0x6b, 0x65, 0x72, 0x73, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x1a, 0x14, 0x2e, 0x4c,
	0x69, 0x73, 0x74, 0x57, 0x6f, 0x72, 0x6b, 0x65, 0x72, 0x73, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e,
	0x73, 0x65, 0x12, 0x3c, 0x0a, 0x0a, 0x52, 0x65, 0x73, 0x63, 0x68, 0x65, 0x64, 0x75, 0x6c, 0x65,
	0x12, 0x16, 0x2e, 0x67, 0x6f, 0x6f, 0x67, 0x6c, 0x65, 0x2e, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x62,
	0x75, 0x66, 0x2e, 0x45, 0x6d, 0x70, 0x74, 0x79, 0x1a, 0x16, 0x2e, 0x67, 0x6f, 0x6f, 0x67, 0x6c,
	0x65, 0x2e, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x62, 0x75, 0x66, 0x2e, 0x45, 0x6d, 0x70, 0x74, 0x79,
	0x42, 0x0e, 0x5a, 0x0c, 0x70, 0x6b, 0x67, 0x2f, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x63, 0x6f, 0x6c,
	0x62, 0x06, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x33,
}

var (
	file_jolt_plugins_remote_execution_administration_proto_rawDescOnce sync.Once
	file_jolt_plugins_remote_execution_administration_proto_rawDescData = file_jolt_plugins_remote_execution_administration_proto_rawDesc
)

func file_jolt_plugins_remote_execution_administration_proto_rawDescGZIP() []byte {
	file_jolt_plugins_remote_execution_administration_proto_rawDescOnce.Do(func() {
		file_jolt_plugins_remote_execution_administration_proto_rawDescData = protoimpl.X.CompressGZIP(file_jolt_plugins_remote_execution_administration_proto_rawDescData)
	})
	return file_jolt_plugins_remote_execution_administration_proto_rawDescData
}

var file_jolt_plugins_remote_execution_administration_proto_msgTypes = make([]protoimpl.MessageInfo, 5)
var file_jolt_plugins_remote_execution_administration_proto_goTypes = []interface{}{
	(*ListBuildsRequest)(nil),        // 0: ListBuildsRequest
	(*ListBuildsResponse)(nil),       // 1: ListBuildsResponse
	(*ListWorkersRequest)(nil),       // 2: ListWorkersRequest
	(*ListWorkersResponse)(nil),      // 3: ListWorkersResponse
	(*ListBuildsResponse_Build)(nil), // 4: ListBuildsResponse.Build
	(*CancelBuildRequest)(nil),       // 5: CancelBuildRequest
	(*emptypb.Empty)(nil),            // 6: google.protobuf.Empty
	(*CancelBuildResponse)(nil),      // 7: CancelBuildResponse
}
var file_jolt_plugins_remote_execution_administration_proto_depIdxs = []int32{
	4, // 0: ListBuildsResponse.builds:type_name -> ListBuildsResponse.Build
	5, // 1: Administration.CancelBuild:input_type -> CancelBuildRequest
	0, // 2: Administration.ListBuilds:input_type -> ListBuildsRequest
	2, // 3: Administration.ListWorkers:input_type -> ListWorkersRequest
	6, // 4: Administration.Reschedule:input_type -> google.protobuf.Empty
	7, // 5: Administration.CancelBuild:output_type -> CancelBuildResponse
	1, // 6: Administration.ListBuilds:output_type -> ListBuildsResponse
	3, // 7: Administration.ListWorkers:output_type -> ListWorkersResponse
	6, // 8: Administration.Reschedule:output_type -> google.protobuf.Empty
	5, // [5:9] is the sub-list for method output_type
	1, // [1:5] is the sub-list for method input_type
	1, // [1:1] is the sub-list for extension type_name
	1, // [1:1] is the sub-list for extension extendee
	0, // [0:1] is the sub-list for field type_name
}

func init() { file_jolt_plugins_remote_execution_administration_proto_init() }
func file_jolt_plugins_remote_execution_administration_proto_init() {
	if File_jolt_plugins_remote_execution_administration_proto != nil {
		return
	}
	file_jolt_plugins_remote_execution_scheduler_proto_init()
	if !protoimpl.UnsafeEnabled {
		file_jolt_plugins_remote_execution_administration_proto_msgTypes[0].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ListBuildsRequest); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_jolt_plugins_remote_execution_administration_proto_msgTypes[1].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ListBuildsResponse); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_jolt_plugins_remote_execution_administration_proto_msgTypes[2].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ListWorkersRequest); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_jolt_plugins_remote_execution_administration_proto_msgTypes[3].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ListWorkersResponse); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
		file_jolt_plugins_remote_execution_administration_proto_msgTypes[4].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ListBuildsResponse_Build); i {
			case 0:
				return &v.state
			case 1:
				return &v.sizeCache
			case 2:
				return &v.unknownFields
			default:
				return nil
			}
		}
	}
	type x struct{}
	out := protoimpl.TypeBuilder{
		File: protoimpl.DescBuilder{
			GoPackagePath: reflect.TypeOf(x{}).PkgPath(),
			RawDescriptor: file_jolt_plugins_remote_execution_administration_proto_rawDesc,
			NumEnums:      0,
			NumMessages:   5,
			NumExtensions: 0,
			NumServices:   1,
		},
		GoTypes:           file_jolt_plugins_remote_execution_administration_proto_goTypes,
		DependencyIndexes: file_jolt_plugins_remote_execution_administration_proto_depIdxs,
		MessageInfos:      file_jolt_plugins_remote_execution_administration_proto_msgTypes,
	}.Build()
	File_jolt_plugins_remote_execution_administration_proto = out.File
	file_jolt_plugins_remote_execution_administration_proto_rawDesc = nil
	file_jolt_plugins_remote_execution_administration_proto_goTypes = nil
	file_jolt_plugins_remote_execution_administration_proto_depIdxs = nil
}
