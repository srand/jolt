#!/bin/sh
# Regenerates the Go protocol stubs in this directory.
#
# Run from the root of the jolt repository. Requires protoc plus the generator
# plugins on PATH at the versions recorded in the headers of the generated files:
#
#   go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.1
#   go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.3.0
#
# Every proto declares go_package = "pkg/protocol", so --go_out=services places
# the output here and puts all messages in a single Go package.

set -e

protoc -I. \
    --go_out=services \
    --go-grpc_out=services \
    jolt/common.proto \
    jolt/plugins/remote_execution/administration.proto \
    jolt/plugins/remote_execution/log.proto \
    jolt/plugins/remote_execution/scheduler.proto \
    jolt/plugins/remote_execution/worker.proto
