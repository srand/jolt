# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: jolt/common.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x11jolt/common.proto\x1a\x1fgoogle/protobuf/timestamp.proto\"-\n\x06\x44igest\x12\x16\n\talgorithm\x18\x01 \x01(\tR\x03\x61lg\x12\x0b\n\x03hex\x18\x02 \x01(\t\"o\n\x07LogLine\x12\x18\n\x05level\x18\x01 \x01(\x0e\x32\t.LogLevel\x12(\n\x04time\x18\x02 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x0f\n\x07\x63ontext\x18\x03 \x01(\t\x12\x0f\n\x07message\x18\x04 \x01(\t\"&\n\x08Property\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t\")\n\x08Platform\x12\x1d\n\nproperties\x18\x01 \x03(\x0b\x32\t.Property\"\x83\x01\n\x04Task\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x10\n\x08identity\x18\x02 \x01(\t\x12\x10\n\x08instance\x18\x03 \x01(\t\x12\r\n\x05taint\x18\x04 \x01(\t\x12\x1d\n\nproperties\x18\x05 \x03(\x0b\x32\t.Property\x12\x1b\n\x08platform\x18\x06 \x01(\x0b\x32\t.Platform\"M\n\tTaskError\x12\x0c\n\x04type\x18\x01 \x01(\t\x12\x10\n\x08location\x18\x02 \x01(\t\x12\x0f\n\x07message\x18\x03 \x01(\t\x12\x0f\n\x07\x64\x65tails\x18\x04 \x01(\t\"5\n\x04\x46ile\x12\x0c\n\x04path\x18\x01 \x01(\t\x12\x0e\n\x06\x64igest\x18\x02 \x01(\t\x12\x0f\n\x07\x63ontent\x18\x03 \x01(\t\"\xf1\x01\n\x07Project\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\"\n\x05paths\x18\x02 \x03(\x0b\x32\x13.Project.SystemPath\x12 \n\x07recipes\x18\x03 \x03(\x0b\x32\x0f.Project.Recipe\x12$\n\tresources\x18\x04 \x03(\x0b\x32\x11.Project.Resource\x1a\x1a\n\nSystemPath\x12\x0c\n\x04path\x18\x01 \x01(\t\x1a\'\n\x08Resource\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\r\n\x05\x61lias\x18\x02 \x01(\t\x1a\'\n\x06Recipe\x12\x0c\n\x04path\x18\x01 \x01(\t\x12\x0f\n\x07workdir\x18\x03 \x01(\t\"`\n\tWorkspace\x12\x0f\n\x07rootdir\x18\x01 \x01(\t\x12\x10\n\x08\x63\x61\x63hedir\x18\x02 \x01(\t\x12\x14\n\x05\x66iles\x18\x03 \x03(\x0b\x32\x05.File\x12\x1a\n\x08projects\x18\x04 \x03(\x0b\x32\x08.Project\"\\\n\x06\x43lient\x12\x0f\n\x07version\x18\x01 \x01(\t\x12\x0c\n\x04tree\x18\x02 \x01(\t\x12\x10\n\x08identity\x18\x03 \x01(\t\x12\x0b\n\x03url\x18\x04 \x01(\t\x12\x14\n\x0crequirements\x18\x05 \x03(\t\"\x99\x02\n\x10\x42uildEnvironment\x12\x17\n\x06\x63lient\x18\x01 \x01(\x0b\x32\x07.Client\x12\x1d\n\tworkspace\x18\x02 \x01(\x0b\x32\n.Workspace\x12\x1d\n\nparameters\x18\x03 \x03(\x0b\x32\t.Property\x12\x1f\n\x17task_default_parameters\x18\x04 \x03(\t\x12+\n\x05tasks\x18\x05 \x03(\x0b\x32\x1c.BuildEnvironment.TasksEntry\x12\x1b\n\x08loglevel\x18\x06 \x01(\x0e\x32\t.LogLevel\x12\x0e\n\x06\x63onfig\x18\x07 \x01(\t\x1a\x33\n\nTasksEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x14\n\x05value\x18\x02 \x01(\x0b\x32\x05.Task:\x02\x38\x01*k\n\x08LogLevel\x12\r\n\tEXCEPTION\x10\x00\x12\t\n\x05\x44\x45\x42UG\x10\x01\x12\x0b\n\x07VERBOSE\x10\x02\x12\n\n\x06STDOUT\x10\x03\x12\x08\n\x04INFO\x10\x04\x12\x0b\n\x07WARNING\x10\x05\x12\t\n\x05\x45RROR\x10\x06\x12\n\n\x06STDERR\x10\x07*_\n\x0b\x42uildStatus\x12\x12\n\x0e\x42UILD_ACCEPTED\x10\x00\x12\x12\n\x0e\x42UILD_REJECTED\x10\x01\x12\x13\n\x0f\x42UILD_COMPLETED\x10\x03\x12\x13\n\x0f\x42UILD_CANCELLED\x10\x04*\xc2\x01\n\nTaskStatus\x12\x0f\n\x0bTASK_QUEUED\x10\x00\x12\x10\n\x0cTASK_RUNNING\x10\x01\x12\x0f\n\x0bTASK_FAILED\x10\x02\x12\x0f\n\x0bTASK_PASSED\x10\x03\x12\x11\n\rTASK_UNSTABLE\x10\x04\x12\x13\n\x0fTASK_DOWNLOADED\x10\x05\x12\x11\n\rTASK_UPLOADED\x10\x06\x12\x10\n\x0cTASK_SKIPPED\x10\x07\x12\x12\n\x0eTASK_CANCELLED\x10\x08\x12\x0e\n\nTASK_ERROR\x10\tB\x0eZ\x0cpkg/protocolb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'jolt.common_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  DESCRIPTOR._serialized_options = b'Z\014pkg/protocol'
  _BUILDENVIRONMENT_TASKSENTRY._options = None
  _BUILDENVIRONMENT_TASKSENTRY._serialized_options = b'8\001'
  _LOGLEVEL._serialized_start=1285
  _LOGLEVEL._serialized_end=1392
  _BUILDSTATUS._serialized_start=1394
  _BUILDSTATUS._serialized_end=1489
  _TASKSTATUS._serialized_start=1492
  _TASKSTATUS._serialized_end=1686
  _DIGEST._serialized_start=54
  _DIGEST._serialized_end=99
  _LOGLINE._serialized_start=101
  _LOGLINE._serialized_end=212
  _PROPERTY._serialized_start=214
  _PROPERTY._serialized_end=252
  _PLATFORM._serialized_start=254
  _PLATFORM._serialized_end=295
  _TASK._serialized_start=298
  _TASK._serialized_end=429
  _TASKERROR._serialized_start=431
  _TASKERROR._serialized_end=508
  _FILE._serialized_start=510
  _FILE._serialized_end=563
  _PROJECT._serialized_start=566
  _PROJECT._serialized_end=807
  _PROJECT_SYSTEMPATH._serialized_start=699
  _PROJECT_SYSTEMPATH._serialized_end=725
  _PROJECT_RESOURCE._serialized_start=727
  _PROJECT_RESOURCE._serialized_end=766
  _PROJECT_RECIPE._serialized_start=768
  _PROJECT_RECIPE._serialized_end=807
  _WORKSPACE._serialized_start=809
  _WORKSPACE._serialized_end=905
  _CLIENT._serialized_start=907
  _CLIENT._serialized_end=999
  _BUILDENVIRONMENT._serialized_start=1002
  _BUILDENVIRONMENT._serialized_end=1283
  _BUILDENVIRONMENT_TASKSENTRY._serialized_start=1232
  _BUILDENVIRONMENT_TASKSENTRY._serialized_end=1283
# @@protoc_insertion_point(module_scope)
