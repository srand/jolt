# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: jolt/plugins/remote_execution/scheduler.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from jolt import common_pb2 as jolt_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n-jolt/plugins/remote_execution/scheduler.proto\x1a\x11jolt/common.proto\"6\n\x0c\x42uildRequest\x12&\n\x0b\x65nvironment\x18\x01 \x01(\x0b\x32\x11.BuildEnvironment\"?\n\rBuildResponse\x12\x1c\n\x06status\x18\x01 \x01(\x0e\x32\x0c.BuildStatus\x12\x10\n\x08\x62uild_id\x18\x02 \x01(\t\"&\n\x12\x43\x61ncelBuildRequest\x12\x10\n\x08\x62uild_id\x18\x01 \x01(\t\"3\n\x13\x43\x61ncelBuildResponse\x12\x1c\n\x06status\x18\x01 \x01(\x0e\x32\x0c.BuildStatus\"0\n\x0bTaskRequest\x12\x10\n\x08\x62uild_id\x18\x01 \x01(\t\x12\x0f\n\x07task_id\x18\x02 \x01(\t\"\xa5\x01\n\nTaskUpdate\x12\x11\n\tworker_id\x18\x01 \x01(\t\x12\x10\n\x08\x62uild_id\x18\x02 \x01(\t\x12\x1d\n\x07request\x18\x03 \x01(\x0b\x32\x0c.TaskRequest\x12\x1b\n\x06status\x18\x04 \x01(\x0e\x32\x0b.TaskStatus\x12\x1a\n\x08loglines\x18\x05 \x03(\x0b\x32\x08.LogLine\x12\x1a\n\x06\x65rrors\x18\x06 \x03(\x0b\x32\n.TaskError2\xa2\x01\n\tScheduler\x12.\n\rScheduleBuild\x12\r.BuildRequest\x1a\x0e.BuildResponse\x12\x38\n\x0b\x43\x61ncelBuild\x12\x13.CancelBuildRequest\x1a\x14.CancelBuildResponse\x12+\n\x0cScheduleTask\x12\x0c.TaskRequest\x1a\x0b.TaskUpdate0\x01\x42\x0eZ\x0cpkg/protocolb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'jolt.plugins.remote_execution.scheduler_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z\014pkg/protocol'
  _BUILDREQUEST._serialized_start=68
  _BUILDREQUEST._serialized_end=122
  _BUILDRESPONSE._serialized_start=124
  _BUILDRESPONSE._serialized_end=187
  _CANCELBUILDREQUEST._serialized_start=189
  _CANCELBUILDREQUEST._serialized_end=227
  _CANCELBUILDRESPONSE._serialized_start=229
  _CANCELBUILDRESPONSE._serialized_end=280
  _TASKREQUEST._serialized_start=282
  _TASKREQUEST._serialized_end=330
  _TASKUPDATE._serialized_start=333
  _TASKUPDATE._serialized_end=498
  _SCHEDULER._serialized_start=501
  _SCHEDULER._serialized_end=663
# @@protoc_insertion_point(module_scope)
