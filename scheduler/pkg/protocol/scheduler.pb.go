// Code generated by protoc-gen-go. DO NOT EDIT.
// versions:
// 	protoc-gen-go v1.28.1
// 	protoc        v3.12.4
// source: jolt/plugins/remote_execution/scheduler.proto

package protocol

import (
	protoreflect "google.golang.org/protobuf/reflect/protoreflect"
	protoimpl "google.golang.org/protobuf/runtime/protoimpl"
	reflect "reflect"
	sync "sync"
)

const (
	// Verify that this generated code is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(20 - protoimpl.MinVersion)
	// Verify that runtime/protoimpl is sufficiently up-to-date.
	_ = protoimpl.EnforceVersion(protoimpl.MaxVersion - 20)
)

// A build request.
type BuildRequest struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// The build environment.
	// Jolt client version, recipes, workspace resources,
	// task identities, etc.
	Environment *BuildEnvironment `protobuf:"bytes,1,opt,name=environment,proto3" json:"environment,omitempty"`
	// Build priority.
	// A higher number means higher priority.
	Priority int32 `protobuf:"varint,2,opt,name=priority,proto3" json:"priority,omitempty"`
	// Stream log lines in real-time
	Logstream bool `protobuf:"varint,3,opt,name=logstream,proto3" json:"logstream,omitempty"`
}

func (x *BuildRequest) Reset() {
	*x = BuildRequest{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[0]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *BuildRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*BuildRequest) ProtoMessage() {}

func (x *BuildRequest) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[0]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use BuildRequest.ProtoReflect.Descriptor instead.
func (*BuildRequest) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP(), []int{0}
}

func (x *BuildRequest) GetEnvironment() *BuildEnvironment {
	if x != nil {
		return x.Environment
	}
	return nil
}

func (x *BuildRequest) GetPriority() int32 {
	if x != nil {
		return x.Priority
	}
	return 0
}

func (x *BuildRequest) GetLogstream() bool {
	if x != nil {
		return x.Logstream
	}
	return false
}

// A build response.
type BuildUpdate struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// Status of the build: accepted, rejected, etc.
	Status BuildStatus `protobuf:"varint,1,opt,name=status,proto3,enum=BuildStatus" json:"status,omitempty"`
	// A scheduler identifier for the build.
	// May be used in calls to e.g. CancelBuild.
	BuildId string `protobuf:"bytes,2,opt,name=build_id,json=buildId,proto3" json:"build_id,omitempty"`
}

func (x *BuildUpdate) Reset() {
	*x = BuildUpdate{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[1]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *BuildUpdate) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*BuildUpdate) ProtoMessage() {}

func (x *BuildUpdate) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[1]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use BuildUpdate.ProtoReflect.Descriptor instead.
func (*BuildUpdate) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP(), []int{1}
}

func (x *BuildUpdate) GetStatus() BuildStatus {
	if x != nil {
		return x.Status
	}
	return BuildStatus_BUILD_ACCEPTED
}

func (x *BuildUpdate) GetBuildId() string {
	if x != nil {
		return x.BuildId
	}
	return ""
}

// Cancel build request.
type CancelBuildRequest struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// Identifier of the build to cancel.
	// See BuildResponse.id.
	BuildId string `protobuf:"bytes,1,opt,name=build_id,json=buildId,proto3" json:"build_id,omitempty"`
}

func (x *CancelBuildRequest) Reset() {
	*x = CancelBuildRequest{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[2]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *CancelBuildRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*CancelBuildRequest) ProtoMessage() {}

func (x *CancelBuildRequest) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[2]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use CancelBuildRequest.ProtoReflect.Descriptor instead.
func (*CancelBuildRequest) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP(), []int{2}
}

func (x *CancelBuildRequest) GetBuildId() string {
	if x != nil {
		return x.BuildId
	}
	return ""
}

type CancelBuildResponse struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// Status of the build after the cancel request.
	Status BuildStatus `protobuf:"varint,1,opt,name=status,proto3,enum=BuildStatus" json:"status,omitempty"`
}

func (x *CancelBuildResponse) Reset() {
	*x = CancelBuildResponse{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[3]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *CancelBuildResponse) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*CancelBuildResponse) ProtoMessage() {}

func (x *CancelBuildResponse) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[3]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use CancelBuildResponse.ProtoReflect.Descriptor instead.
func (*CancelBuildResponse) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP(), []int{3}
}

func (x *CancelBuildResponse) GetStatus() BuildStatus {
	if x != nil {
		return x.Status
	}
	return BuildStatus_BUILD_ACCEPTED
}

// A task execution request.
// Sent by clients to the scheduler.
// The client must ensure that all task dependencies have
// already executed before scheduling a task.
type TaskRequest struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// The build request that the task belongs to.
	BuildId string `protobuf:"bytes,1,opt,name=build_id,json=buildId,proto3" json:"build_id,omitempty"`
	// The identity of the task to execute.
	TaskId string `protobuf:"bytes,2,opt,name=task_id,json=taskId,proto3" json:"task_id,omitempty"`
}

func (x *TaskRequest) Reset() {
	*x = TaskRequest{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[4]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *TaskRequest) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*TaskRequest) ProtoMessage() {}

func (x *TaskRequest) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[4]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use TaskRequest.ProtoReflect.Descriptor instead.
func (*TaskRequest) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP(), []int{4}
}

func (x *TaskRequest) GetBuildId() string {
	if x != nil {
		return x.BuildId
	}
	return ""
}

func (x *TaskRequest) GetTaskId() string {
	if x != nil {
		return x.TaskId
	}
	return ""
}

// The allocated worker
type WorkerAllocation struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// Worker id
	Id string `protobuf:"bytes,1,opt,name=id,proto3" json:"id,omitempty"`
}

func (x *WorkerAllocation) Reset() {
	*x = WorkerAllocation{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[5]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *WorkerAllocation) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*WorkerAllocation) ProtoMessage() {}

func (x *WorkerAllocation) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[5]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use WorkerAllocation.ProtoReflect.Descriptor instead.
func (*WorkerAllocation) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP(), []int{5}
}

func (x *WorkerAllocation) GetId() string {
	if x != nil {
		return x.Id
	}
	return ""
}

// An update on the progress of an executing task.
type TaskUpdate struct {
	state         protoimpl.MessageState
	sizeCache     protoimpl.SizeCache
	unknownFields protoimpl.UnknownFields

	// The original task execution request.
	Request *TaskRequest `protobuf:"bytes,1,opt,name=request,proto3" json:"request,omitempty"`
	// The current status of the task.
	Status TaskStatus `protobuf:"varint,2,opt,name=status,proto3,enum=TaskStatus" json:"status,omitempty"`
	// The worker that is assigned to execute the task.
	Worker *WorkerAllocation `protobuf:"bytes,3,opt,name=worker,proto3" json:"worker,omitempty"`
	// Log lines output by the task, if any.
	Loglines []*LogLine `protobuf:"bytes,4,rep,name=loglines,proto3" json:"loglines,omitempty"`
	// Errors reported by the task
	Errors []*TaskError `protobuf:"bytes,5,rep,name=errors,proto3" json:"errors,omitempty"`
}

func (x *TaskUpdate) Reset() {
	*x = TaskUpdate{}
	if protoimpl.UnsafeEnabled {
		mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[6]
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		ms.StoreMessageInfo(mi)
	}
}

func (x *TaskUpdate) String() string {
	return protoimpl.X.MessageStringOf(x)
}

func (*TaskUpdate) ProtoMessage() {}

func (x *TaskUpdate) ProtoReflect() protoreflect.Message {
	mi := &file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[6]
	if protoimpl.UnsafeEnabled && x != nil {
		ms := protoimpl.X.MessageStateOf(protoimpl.Pointer(x))
		if ms.LoadMessageInfo() == nil {
			ms.StoreMessageInfo(mi)
		}
		return ms
	}
	return mi.MessageOf(x)
}

// Deprecated: Use TaskUpdate.ProtoReflect.Descriptor instead.
func (*TaskUpdate) Descriptor() ([]byte, []int) {
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP(), []int{6}
}

func (x *TaskUpdate) GetRequest() *TaskRequest {
	if x != nil {
		return x.Request
	}
	return nil
}

func (x *TaskUpdate) GetStatus() TaskStatus {
	if x != nil {
		return x.Status
	}
	return TaskStatus_TASK_QUEUED
}

func (x *TaskUpdate) GetWorker() *WorkerAllocation {
	if x != nil {
		return x.Worker
	}
	return nil
}

func (x *TaskUpdate) GetLoglines() []*LogLine {
	if x != nil {
		return x.Loglines
	}
	return nil
}

func (x *TaskUpdate) GetErrors() []*TaskError {
	if x != nil {
		return x.Errors
	}
	return nil
}

var File_jolt_plugins_remote_execution_scheduler_proto protoreflect.FileDescriptor

var file_jolt_plugins_remote_execution_scheduler_proto_rawDesc = []byte{
	0x0a, 0x2d, 0x6a, 0x6f, 0x6c, 0x74, 0x2f, 0x70, 0x6c, 0x75, 0x67, 0x69, 0x6e, 0x73, 0x2f, 0x72,
	0x65, 0x6d, 0x6f, 0x74, 0x65, 0x5f, 0x65, 0x78, 0x65, 0x63, 0x75, 0x74, 0x69, 0x6f, 0x6e, 0x2f,
	0x73, 0x63, 0x68, 0x65, 0x64, 0x75, 0x6c, 0x65, 0x72, 0x2e, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x1a,
	0x11, 0x6a, 0x6f, 0x6c, 0x74, 0x2f, 0x63, 0x6f, 0x6d, 0x6d, 0x6f, 0x6e, 0x2e, 0x70, 0x72, 0x6f,
	0x74, 0x6f, 0x22, 0x7d, 0x0a, 0x0c, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x52, 0x65, 0x71, 0x75, 0x65,
	0x73, 0x74, 0x12, 0x33, 0x0a, 0x0b, 0x65, 0x6e, 0x76, 0x69, 0x72, 0x6f, 0x6e, 0x6d, 0x65, 0x6e,
	0x74, 0x18, 0x01, 0x20, 0x01, 0x28, 0x0b, 0x32, 0x11, 0x2e, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x45,
	0x6e, 0x76, 0x69, 0x72, 0x6f, 0x6e, 0x6d, 0x65, 0x6e, 0x74, 0x52, 0x0b, 0x65, 0x6e, 0x76, 0x69,
	0x72, 0x6f, 0x6e, 0x6d, 0x65, 0x6e, 0x74, 0x12, 0x1a, 0x0a, 0x08, 0x70, 0x72, 0x69, 0x6f, 0x72,
	0x69, 0x74, 0x79, 0x18, 0x02, 0x20, 0x01, 0x28, 0x05, 0x52, 0x08, 0x70, 0x72, 0x69, 0x6f, 0x72,
	0x69, 0x74, 0x79, 0x12, 0x1c, 0x0a, 0x09, 0x6c, 0x6f, 0x67, 0x73, 0x74, 0x72, 0x65, 0x61, 0x6d,
	0x18, 0x03, 0x20, 0x01, 0x28, 0x08, 0x52, 0x09, 0x6c, 0x6f, 0x67, 0x73, 0x74, 0x72, 0x65, 0x61,
	0x6d, 0x22, 0x4e, 0x0a, 0x0b, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x55, 0x70, 0x64, 0x61, 0x74, 0x65,
	0x12, 0x24, 0x0a, 0x06, 0x73, 0x74, 0x61, 0x74, 0x75, 0x73, 0x18, 0x01, 0x20, 0x01, 0x28, 0x0e,
	0x32, 0x0c, 0x2e, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x53, 0x74, 0x61, 0x74, 0x75, 0x73, 0x52, 0x06,
	0x73, 0x74, 0x61, 0x74, 0x75, 0x73, 0x12, 0x19, 0x0a, 0x08, 0x62, 0x75, 0x69, 0x6c, 0x64, 0x5f,
	0x69, 0x64, 0x18, 0x02, 0x20, 0x01, 0x28, 0x09, 0x52, 0x07, 0x62, 0x75, 0x69, 0x6c, 0x64, 0x49,
	0x64, 0x22, 0x2f, 0x0a, 0x12, 0x43, 0x61, 0x6e, 0x63, 0x65, 0x6c, 0x42, 0x75, 0x69, 0x6c, 0x64,
	0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x12, 0x19, 0x0a, 0x08, 0x62, 0x75, 0x69, 0x6c, 0x64,
	0x5f, 0x69, 0x64, 0x18, 0x01, 0x20, 0x01, 0x28, 0x09, 0x52, 0x07, 0x62, 0x75, 0x69, 0x6c, 0x64,
	0x49, 0x64, 0x22, 0x3b, 0x0a, 0x13, 0x43, 0x61, 0x6e, 0x63, 0x65, 0x6c, 0x42, 0x75, 0x69, 0x6c,
	0x64, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73, 0x65, 0x12, 0x24, 0x0a, 0x06, 0x73, 0x74, 0x61,
	0x74, 0x75, 0x73, 0x18, 0x01, 0x20, 0x01, 0x28, 0x0e, 0x32, 0x0c, 0x2e, 0x42, 0x75, 0x69, 0x6c,
	0x64, 0x53, 0x74, 0x61, 0x74, 0x75, 0x73, 0x52, 0x06, 0x73, 0x74, 0x61, 0x74, 0x75, 0x73, 0x22,
	0x41, 0x0a, 0x0b, 0x54, 0x61, 0x73, 0x6b, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x12, 0x19,
	0x0a, 0x08, 0x62, 0x75, 0x69, 0x6c, 0x64, 0x5f, 0x69, 0x64, 0x18, 0x01, 0x20, 0x01, 0x28, 0x09,
	0x52, 0x07, 0x62, 0x75, 0x69, 0x6c, 0x64, 0x49, 0x64, 0x12, 0x17, 0x0a, 0x07, 0x74, 0x61, 0x73,
	0x6b, 0x5f, 0x69, 0x64, 0x18, 0x02, 0x20, 0x01, 0x28, 0x09, 0x52, 0x06, 0x74, 0x61, 0x73, 0x6b,
	0x49, 0x64, 0x22, 0x22, 0x0a, 0x10, 0x57, 0x6f, 0x72, 0x6b, 0x65, 0x72, 0x41, 0x6c, 0x6c, 0x6f,
	0x63, 0x61, 0x74, 0x69, 0x6f, 0x6e, 0x12, 0x0e, 0x0a, 0x02, 0x69, 0x64, 0x18, 0x01, 0x20, 0x01,
	0x28, 0x09, 0x52, 0x02, 0x69, 0x64, 0x22, 0xce, 0x01, 0x0a, 0x0a, 0x54, 0x61, 0x73, 0x6b, 0x55,
	0x70, 0x64, 0x61, 0x74, 0x65, 0x12, 0x26, 0x0a, 0x07, 0x72, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74,
	0x18, 0x01, 0x20, 0x01, 0x28, 0x0b, 0x32, 0x0c, 0x2e, 0x54, 0x61, 0x73, 0x6b, 0x52, 0x65, 0x71,
	0x75, 0x65, 0x73, 0x74, 0x52, 0x07, 0x72, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x12, 0x23, 0x0a,
	0x06, 0x73, 0x74, 0x61, 0x74, 0x75, 0x73, 0x18, 0x02, 0x20, 0x01, 0x28, 0x0e, 0x32, 0x0b, 0x2e,
	0x54, 0x61, 0x73, 0x6b, 0x53, 0x74, 0x61, 0x74, 0x75, 0x73, 0x52, 0x06, 0x73, 0x74, 0x61, 0x74,
	0x75, 0x73, 0x12, 0x29, 0x0a, 0x06, 0x77, 0x6f, 0x72, 0x6b, 0x65, 0x72, 0x18, 0x03, 0x20, 0x01,
	0x28, 0x0b, 0x32, 0x11, 0x2e, 0x57, 0x6f, 0x72, 0x6b, 0x65, 0x72, 0x41, 0x6c, 0x6c, 0x6f, 0x63,
	0x61, 0x74, 0x69, 0x6f, 0x6e, 0x52, 0x06, 0x77, 0x6f, 0x72, 0x6b, 0x65, 0x72, 0x12, 0x24, 0x0a,
	0x08, 0x6c, 0x6f, 0x67, 0x6c, 0x69, 0x6e, 0x65, 0x73, 0x18, 0x04, 0x20, 0x03, 0x28, 0x0b, 0x32,
	0x08, 0x2e, 0x4c, 0x6f, 0x67, 0x4c, 0x69, 0x6e, 0x65, 0x52, 0x08, 0x6c, 0x6f, 0x67, 0x6c, 0x69,
	0x6e, 0x65, 0x73, 0x12, 0x22, 0x0a, 0x06, 0x65, 0x72, 0x72, 0x6f, 0x72, 0x73, 0x18, 0x05, 0x20,
	0x03, 0x28, 0x0b, 0x32, 0x0a, 0x2e, 0x54, 0x61, 0x73, 0x6b, 0x45, 0x72, 0x72, 0x6f, 0x72, 0x52,
	0x06, 0x65, 0x72, 0x72, 0x6f, 0x72, 0x73, 0x32, 0xa2, 0x01, 0x0a, 0x09, 0x53, 0x63, 0x68, 0x65,
	0x64, 0x75, 0x6c, 0x65, 0x72, 0x12, 0x2e, 0x0a, 0x0d, 0x53, 0x63, 0x68, 0x65, 0x64, 0x75, 0x6c,
	0x65, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x12, 0x0d, 0x2e, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x52, 0x65,
	0x71, 0x75, 0x65, 0x73, 0x74, 0x1a, 0x0c, 0x2e, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x55, 0x70, 0x64,
	0x61, 0x74, 0x65, 0x30, 0x01, 0x12, 0x38, 0x0a, 0x0b, 0x43, 0x61, 0x6e, 0x63, 0x65, 0x6c, 0x42,
	0x75, 0x69, 0x6c, 0x64, 0x12, 0x13, 0x2e, 0x43, 0x61, 0x6e, 0x63, 0x65, 0x6c, 0x42, 0x75, 0x69,
	0x6c, 0x64, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x1a, 0x14, 0x2e, 0x43, 0x61, 0x6e, 0x63,
	0x65, 0x6c, 0x42, 0x75, 0x69, 0x6c, 0x64, 0x52, 0x65, 0x73, 0x70, 0x6f, 0x6e, 0x73, 0x65, 0x12,
	0x2b, 0x0a, 0x0c, 0x53, 0x63, 0x68, 0x65, 0x64, 0x75, 0x6c, 0x65, 0x54, 0x61, 0x73, 0x6b, 0x12,
	0x0c, 0x2e, 0x54, 0x61, 0x73, 0x6b, 0x52, 0x65, 0x71, 0x75, 0x65, 0x73, 0x74, 0x1a, 0x0b, 0x2e,
	0x54, 0x61, 0x73, 0x6b, 0x55, 0x70, 0x64, 0x61, 0x74, 0x65, 0x30, 0x01, 0x42, 0x0e, 0x5a, 0x0c,
	0x70, 0x6b, 0x67, 0x2f, 0x70, 0x72, 0x6f, 0x74, 0x6f, 0x63, 0x6f, 0x6c, 0x62, 0x06, 0x70, 0x72,
	0x6f, 0x74, 0x6f, 0x33,
}

var (
	file_jolt_plugins_remote_execution_scheduler_proto_rawDescOnce sync.Once
	file_jolt_plugins_remote_execution_scheduler_proto_rawDescData = file_jolt_plugins_remote_execution_scheduler_proto_rawDesc
)

func file_jolt_plugins_remote_execution_scheduler_proto_rawDescGZIP() []byte {
	file_jolt_plugins_remote_execution_scheduler_proto_rawDescOnce.Do(func() {
		file_jolt_plugins_remote_execution_scheduler_proto_rawDescData = protoimpl.X.CompressGZIP(file_jolt_plugins_remote_execution_scheduler_proto_rawDescData)
	})
	return file_jolt_plugins_remote_execution_scheduler_proto_rawDescData
}

var file_jolt_plugins_remote_execution_scheduler_proto_msgTypes = make([]protoimpl.MessageInfo, 7)
var file_jolt_plugins_remote_execution_scheduler_proto_goTypes = []interface{}{
	(*BuildRequest)(nil),        // 0: BuildRequest
	(*BuildUpdate)(nil),         // 1: BuildUpdate
	(*CancelBuildRequest)(nil),  // 2: CancelBuildRequest
	(*CancelBuildResponse)(nil), // 3: CancelBuildResponse
	(*TaskRequest)(nil),         // 4: TaskRequest
	(*WorkerAllocation)(nil),    // 5: WorkerAllocation
	(*TaskUpdate)(nil),          // 6: TaskUpdate
	(*BuildEnvironment)(nil),    // 7: BuildEnvironment
	(BuildStatus)(0),            // 8: BuildStatus
	(TaskStatus)(0),             // 9: TaskStatus
	(*LogLine)(nil),             // 10: LogLine
	(*TaskError)(nil),           // 11: TaskError
}
var file_jolt_plugins_remote_execution_scheduler_proto_depIdxs = []int32{
	7,  // 0: BuildRequest.environment:type_name -> BuildEnvironment
	8,  // 1: BuildUpdate.status:type_name -> BuildStatus
	8,  // 2: CancelBuildResponse.status:type_name -> BuildStatus
	4,  // 3: TaskUpdate.request:type_name -> TaskRequest
	9,  // 4: TaskUpdate.status:type_name -> TaskStatus
	5,  // 5: TaskUpdate.worker:type_name -> WorkerAllocation
	10, // 6: TaskUpdate.loglines:type_name -> LogLine
	11, // 7: TaskUpdate.errors:type_name -> TaskError
	0,  // 8: Scheduler.ScheduleBuild:input_type -> BuildRequest
	2,  // 9: Scheduler.CancelBuild:input_type -> CancelBuildRequest
	4,  // 10: Scheduler.ScheduleTask:input_type -> TaskRequest
	1,  // 11: Scheduler.ScheduleBuild:output_type -> BuildUpdate
	3,  // 12: Scheduler.CancelBuild:output_type -> CancelBuildResponse
	6,  // 13: Scheduler.ScheduleTask:output_type -> TaskUpdate
	11, // [11:14] is the sub-list for method output_type
	8,  // [8:11] is the sub-list for method input_type
	8,  // [8:8] is the sub-list for extension type_name
	8,  // [8:8] is the sub-list for extension extendee
	0,  // [0:8] is the sub-list for field type_name
}

func init() { file_jolt_plugins_remote_execution_scheduler_proto_init() }
func file_jolt_plugins_remote_execution_scheduler_proto_init() {
	if File_jolt_plugins_remote_execution_scheduler_proto != nil {
		return
	}
	file_jolt_common_proto_init()
	if !protoimpl.UnsafeEnabled {
		file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[0].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*BuildRequest); i {
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
		file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[1].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*BuildUpdate); i {
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
		file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[2].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*CancelBuildRequest); i {
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
		file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[3].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*CancelBuildResponse); i {
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
		file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[4].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*TaskRequest); i {
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
		file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[5].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*WorkerAllocation); i {
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
		file_jolt_plugins_remote_execution_scheduler_proto_msgTypes[6].Exporter = func(v interface{}, i int) interface{} {
			switch v := v.(*TaskUpdate); i {
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
			RawDescriptor: file_jolt_plugins_remote_execution_scheduler_proto_rawDesc,
			NumEnums:      0,
			NumMessages:   7,
			NumExtensions: 0,
			NumServices:   1,
		},
		GoTypes:           file_jolt_plugins_remote_execution_scheduler_proto_goTypes,
		DependencyIndexes: file_jolt_plugins_remote_execution_scheduler_proto_depIdxs,
		MessageInfos:      file_jolt_plugins_remote_execution_scheduler_proto_msgTypes,
	}.Build()
	File_jolt_plugins_remote_execution_scheduler_proto = out.File
	file_jolt_plugins_remote_execution_scheduler_proto_rawDesc = nil
	file_jolt_plugins_remote_execution_scheduler_proto_goTypes = nil
	file_jolt_plugins_remote_execution_scheduler_proto_depIdxs = nil
}
