package scheduler

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
)

func TestGrpcPermission(t *testing.T) {
	assert.Equal(t, BuildPermission, GrpcPermission(protocol.Scheduler_ScheduleBuild_FullMethodName))
	assert.Equal(t, BuildPermission, GrpcPermission(protocol.Scheduler_ScheduleTask_FullMethodName))
	assert.Equal(t, WorkerPermission, GrpcPermission(protocol.Worker_GetInstructions_FullMethodName))
	assert.Equal(t, WorkerPermission, GrpcPermission(protocol.Worker_GetTasks_FullMethodName))
	assert.Equal(t, ReadPermission, GrpcPermission(protocol.Administration_StreamEvents_FullMethodName))
	assert.Equal(t, ReadPermission, GrpcPermission(protocol.LogStash_ReadLog_FullMethodName))
	assert.Equal(t, AdminPermission, GrpcPermission(protocol.Administration_CancelBuild_FullMethodName))
	assert.Equal(t, AdminPermission, GrpcPermission("/grpc.reflection.v1.ServerReflection/ServerReflectionInfo"))
}

func TestHttpPermission(t *testing.T) {
	assert.Equal(t, ReadPermission, HttpPermission(httptest.NewRequest(http.MethodGet, "/logs/123", nil)))
	assert.Equal(t, ReadPermission, HttpPermission(httptest.NewRequest(http.MethodGet, "/metrics", nil)))
	assert.Equal(t, AdminPermission, HttpPermission(httptest.NewRequest(http.MethodGet, "/debug/pprof/", nil)))
}
