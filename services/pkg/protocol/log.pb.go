// Code generated by protoc-gen-go. DO NOT EDIT.
// versions:
// 	protoc-gen-go v1.31.0
// 	protoc        v4.24.4
// source: services/pkg/logstash/log.proto

package protocol

import (
	protoreflect "google.golang.org/protobuf/reflect/protoreflect"
	protoimpl "google.golang.org/protobuf/runtime/protoimpl"
	timestamppb "google.golang.org/protobuf/types/known/timestamppb"
	reflect "reflect"
	sync "sync"
)

const (
	// Verify that this generated code is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(20 - protoimpl.MinVersion)
	// Verify that runtime/protoimpl is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(protoimpl.MaxVersion - 20)
)

// Request to read a log file.
type ReadLogRequest struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// Log stream identifier
	Id string `protobuf:"bytes,1,opt,name=id,proto3" json:"id,omitempty"`
	// Include records before and after these timestamps.
	// May be left empty if no filtering is desired.
	Before *timestamppb.Timestamp `protobuf:"bytes,2,opt,name=before,proto3" json:"before,omitempty"`
	After  *timestamppb.Timestamp `protobuf:"bytes,3,opt,name=after,proto3" json:"after,omitempty"`
}

func (x *ReadLogRequest) Reset() {
	*x = ReadLogRequest{}
	if protoimpl.UnsafeEnabled {
		mi := &file_services_pkg_logstash_log_proto_msgTypes[0]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ReadLogRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ReadLogRequest) ProtoMessage() {}

func (x *ReadLogRequest) ProtoReflect() protoreflect.Message {
	mi := &file_services_pkg_logstash_log_proto_msgTypes[0]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ReadLogRequest.ProtoReflect.Descriptor instead.
func (*ReadLogRequest) Descriptor() ([]byte, []int) {
	return file_services_pkg_logstash_log_proto_rawDescGZIP(), []int{0}
}

func (x *ReadLogRequest) GetId() string {
	if x != nil {
		return x.Id
	}
	return ""
}

func (x *ReadLogRequest) GetBefore() *timestamppb.Timestamp {
	if x != nil {
		return x.Before
	}
	return nil
}

func (x *ReadLogRequest) GetAfter() *timestamppb.Timestamp {
	if x != nil {
		return x.After
	}
	return nil
}

// Response with log file data
type ReadLogResponse struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// Log stream identifier
	Id string `protobuf:"bytes,1,opt,name=id,proto3" json:"id,omitempty"`
	// List of logline records
	Loglines []*LogLine `protobuf:"bytes,2,rep,name=loglines,proto3" json:"loglines,omitempty"`
}

func (x *ReadLogResponse) Reset() {
	*x = ReadLogResponse{}
	if protoimpl.UnsafeEnabled {
		mi := &file_services_pkg_logstash_log_proto_msgTypes[1]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *ReadLogResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*ReadLogResponse) ProtoMessage() {}

func (x *ReadLogResponse) ProtoReflect() protoreflect.Message {
	mi := &file_services_pkg_logstash_log_proto_msgTypes[1]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use ReadLogResponse.ProtoReflect.Descriptor instead.
func (*ReadLogResponse) Descriptor() ([]byte, []int) {
	return file_services_pkg_logstash_log_proto_rawDescGZIP(), []int{1}
}

func (x *ReadLogResponse) GetId() string {
	if x != nil {
		return x.Id
	}
	return ""
}

func (x *ReadLogResponse) GetLoglines() []*LogLine {
	if x != nil {
		return x.Loglines
	}
	return nil
}

var File_services_pkg_logstash_log_proto protoreflect.FileDescriptor

var file_services_pkg_logstash_log_proto_rawDesc = []byte{
	0x0a, 0x1f, 0x73, 0x65, 0x72, 0x76, 0x69, 0x63, 0x65, 0x73, 0x2f, 0x70, 0x6b, 0x67, 0x2f, 0x6c,
	0x6f, 0x67, 0x73, 0x74, 0x61, 0x73, 0x68, 0x2f, 0x6c, 0x6f, 0x67, 0x2e, 0x70, 0x72, 0x6f, 0x74,
	0x6f, 0x1a, 0x1f, 0x67, 0x6f, 0x6f, 0x67, 0x6c, 0x65, 0x2f, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x62,
	0x75, 0x66, 0x2f, 0x74, 0x69, 0x6d, 0x65, 0x73, 0x74, 0x61, 0x6d, 0x70, 0x2e, 0x70, 0x72, 0x6f,
	0x74, 0x6f, 0x1a, 0x11, 0x6a, 0x6f, 0x6c, 0x74, 0x2f, 0x63, 0x6f, 0x6d, 0x6d, 0x6f, 0x6e, 0x2e,
	0x70, 0x72, 0x6f, 0x74, 0x6f, 0x22, 0x86, 0x01, 0x0a, 0x0e, 0x52, 0x65, 0x61, 0x64, 0x4c, 0x6f,
	0x67, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x12, 0x0e, 0x0a, 0x02, 0x69, 0x64, 0x18, 0x01,
	0x20, 0x01, 0x28, 0x09, 0x52, 0x02, 0x69, 0x64, 0x12, 0x32, 0x0a, 0x06, 0x62, 0x65, 0x66, 0x6f,
	0x72, 0x65, 0x18, 0x02, 0x20, 0x01, 0x28, 0x0b, 0x32, 0x1a, 0x2e, 0x67, 0x6f, 0x6f, 0x67, 0x6c,
	0x65, 0x2e, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x62, 0x75, 0x66, 0x2e, 0x54, 0x69, 0x6d, 0x65, 0x73,
	0x74, 0x61, 0x6d, 0x70, 0x52, 0x06, 0x62, 0x65, 0x66, 0x6f, 0x72, 0x65, 0x12, 0x30, 0x0a, 0x05,
	0x61, 0x66, 0x74, 0x65, 0x72, 0x18, 0x03, 0x20, 0x01, 0x28, 0x0b, 0x32, 0x1a, 0x2e, 0x67, 0x6f,
	0x6f, 0x67, 0x6c, 0x65, 0x2e, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x62, 0x75, 0x66, 0x2e, 0x54, 0x69,
	0x6d, 0x65, 0x73, 0x74, 0x61, 0x6d, 0x70, 0x52, 0x05, 0x61, 0x66, 0x74, 0x65, 0x72, 0x22, 0x47,
	0x0a, 0x0f, 0x52, 0x65, 0x61, 0x64, 0x4c, 0x6f, 0x67, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73,
	0x65, 0x12, 0x0e, 0x0a, 0x02, 0x69, 0x64, 0x18, 0x01, 0x20, 0x01, 0x28, 0x09, 0x52, 0x02, 0x69,
	0x64, 0x12, 0x24, 0x0a, 0x08, 0x6c, 0x6f, 0x67, 0x6c, 0x69, 0x6e, 0x65, 0x73, 0x18, 0x02, 0x20,
	0x03, 0x28, 0x0b, 0x32, 0x08, 0x2e, 0x4c, 0x6f, 0x67, 0x4c, 0x69, 0x6e, 0x65, 0x52, 0x08, 0x6c,
	0x6f, 0x67, 0x6c, 0x69, 0x6e, 0x65, 0x73, 0x32, 0x3a, 0x0a, 0x08, 0x4c, 0x6f, 0x67, 0x53, 0x74,
	0x61, 0x73, 0x68, 0x12, 0x2e, 0x0a, 0x07, 0x52, 0x65, 0x61, 0x64, 0x4c, 0x6f, 0x67, 0x12, 0x0f,
	0x2e, 0x52, 0x65, 0x61, 0x64, 0x4c, 0x6f, 0x67, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x1a,
	0x10, 0x2e, 0x52, 0x65, 0x61, 0x64, 0x4c, 0x6f, 0x67, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73,
	0x65, 0x30, 0x01, 0x42, 0x0e, 0x5a, 0x0c, 0x70, 0x6b, 0x67, 0x2f, 0x70, 0x72, 0x6f, 0x74, 0x6f,
	0x63, 0x6f, 0x6c, 0x62, 0x06, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x33,
}

var (
	file_services_pkg_logstash_log_proto_rawDescOnce sync.Once
	file_services_pkg_logstash_log_proto_rawDescData = file_services_pkg_logstash_log_proto_rawDesc
)

func file_services_pkg_logstash_log_proto_rawDescGZIP() []byte {
	file_services_pkg_logstash_log_proto_rawDescOnce.Do(func() {
		file_services_pkg_logstash_log_proto_rawDescData = protoimpl.X.CompressGZIP(file_services_pkg_logstash_log_proto_rawDescData)
	})
	return file_services_pkg_logstash_log_proto_rawDescData
}

var file_services_pkg_logstash_log_proto_msgTypes = make([]protoimpl.MessageInfo, 2)
var file_services_pkg_logstash_log_proto_goTypes = []interface{}{
	(*ReadLogRequest)(nil),        // 0: ReadLogRequest
	(*ReadLogResponse)(nil),       // 1: ReadLogResponse
	(*timestamppb.Timestamp)(nil), // 2: google.protobuf.Timestamp
	(*LogLine)(nil),               // 3: LogLine
}
var file_services_pkg_logstash_log_proto_depIdxs = []int32{
	2, // 0: ReadLogRequest.before:type_name -> google.protobuf.Timestamp
	2, // 1: ReadLogRequest.after:type_name -> google.protobuf.Timestamp
	3, // 2: ReadLogResponse.loglines:type_name -> LogLine
	0, // 3: LogStash.ReadLog:input_type -> ReadLogRequest
	1, // 4: LogStash.ReadLog:output_type -> ReadLogResponse
	4, // [4:5] is the sub-list for method output_type
	3, // [3:4] is the sub-list for method input_type
	3, // [3:3] is the sub-list for extension type_name
	3, // [3:3] is the sub-list for extension extendee
	0, // [0:3] is the sub-list for field type_name
}

func init() { file_services_pkg_logstash_log_proto_init() }
func file_services_pkg_logstash_log_proto_init() {
	if File_services_pkg_logstash_log_proto != nil {
		return
	}
	file_jolt_common_proto_init()
	if !protoimpl.UnsafeEnabled {
		file_services_pkg_logstash_log_proto_msgTypes[0].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ReadLogRequest); i {
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
		file_services_pkg_logstash_log_proto_msgTypes[1].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*ReadLogResponse); i {
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
			RawDescriptor: file_services_pkg_logstash_log_proto_rawDesc,
			NumEnums:      0,
			NumMessages:   2,
			NumExtensions: 0,
			NumServices:   1,
		},
		GoTypes:           file_services_pkg_logstash_log_proto_goTypes,
		DependencyIndexes: file_services_pkg_logstash_log_proto_depIdxs,
		MessageInfos:      file_services_pkg_logstash_log_proto_msgTypes,
	}.Build()
	File_services_pkg_logstash_log_proto = out.File
	file_services_pkg_logstash_log_proto_rawDesc = nil
	file_services_pkg_logstash_log_proto_goTypes = nil
	file_services_pkg_logstash_log_proto_depIdxs = nil
}
