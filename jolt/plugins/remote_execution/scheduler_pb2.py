# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: jolt/plugins/remote_execution/scheduler.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from jolt import common_pb2 as jolt_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n-jolt/plugins/remote_execution/scheduler.proto\x1a\x11jolt/common.proto\"[\n\x0c\x42uildRequest\x12&\n\x0b\x65nvironment\x18\x01 \x01(\x0b\x32\x11.BuildEnvironment\x12\x10\n\x08priority\x18\x02 \x01(\x05\x12\x11\n\tlogstream\x18\x03 \x01(\x08\"=\n\x0b\x42uildUpdate\x12\x1c\n\x06status\x18\x01 \x01(\x0e\x32\x0c.BuildStatus\x12\x10\n\x08\x62uild_id\x18\x02 \x01(\t\"&\n\x12\x43\x61ncelBuildRequest\x12\x10\n\x08\x62uild_id\x18\x01 \x01(\t\"3\n\x13\x43\x61ncelBuildResponse\x12\x1c\n\x06status\x18\x01 \x01(\x0e\x32\x0c.BuildStatus\"0\n\x0bTaskRequest\x12\x10\n\x08\x62uild_id\x18\x01 \x01(\t\x12\x0f\n\x07task_id\x18\x02 \x01(\t\"0\n\x10WorkerAllocation\x12\n\n\x02id\x18\x01 \x01(\t\x12\x10\n\x08hostname\x18\x02 \x01(\t\"\xa3\x01\n\nTaskUpdate\x12\x1d\n\x07request\x18\x01 \x01(\x0b\x32\x0c.TaskRequest\x12\x1b\n\x06status\x18\x02 \x01(\x0e\x32\x0b.TaskStatus\x12!\n\x06worker\x18\x03 \x01(\x0b\x32\x11.WorkerAllocation\x12\x1a\n\x08loglines\x18\x04 \x03(\x0b\x32\x08.LogLine\x12\x1a\n\x06\x65rrors\x18\x05 \x03(\x0b\x32\n.TaskError2\xa2\x01\n\tScheduler\x12.\n\rScheduleBuild\x12\r.BuildRequest\x1a\x0c.BuildUpdate0\x01\x12\x38\n\x0b\x43\x61ncelBuild\x12\x13.CancelBuildRequest\x1a\x14.CancelBuildResponse\x12+\n\x0cScheduleTask\x12\x0c.TaskRequest\x1a\x0b.TaskUpdate0\x01\x42\x0eZ\x0cpkg/protocolb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'jolt.plugins.remote_execution.scheduler_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
  _globals['DESCRIPTOR']._options = None
  _globals['DESCRIPTOR']._serialized_options = b'Z\014pkg/protocol'
  _globals['_BUILDREQUEST']._serialized_start=68
  _globals['_BUILDREQUEST']._serialized_end=159
  _globals['_BUILDUPDATE']._serialized_start=161
  _globals['_BUILDUPDATE']._serialized_end=222
  _globals['_CANCELBUILDREQUEST']._serialized_start=224
  _globals['_CANCELBUILDREQUEST']._serialized_end=262
  _globals['_CANCELBUILDRESPONSE']._serialized_start=264
  _globals['_CANCELBUILDRESPONSE']._serialized_end=315
  _globals['_TASKREQUEST']._serialized_start=317
  _globals['_TASKREQUEST']._serialized_end=365
  _globals['_WORKERALLOCATION']._serialized_start=367
  _globals['_WORKERALLOCATION']._serialized_end=415
  _globals['_TASKUPDATE']._serialized_start=418
  _globals['_TASKUPDATE']._serialized_end=581
  _globals['_SCHEDULER']._serialized_start=584
  _globals['_SCHEDULER']._serialized_end=746
# @@protoc_insertion_point(module_scope)
