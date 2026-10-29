package scheduler

import (
	"net/http"
	"strings"

	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

const (
	// Build, cancel the builds that the client submitted, and run their
	// tasks. Clients that build also need to read, to see the logs of their
	// tasks.
	BuildPermission auth.Permission = "build"
	// Execute tasks, required by workers and the executors they start.
	WorkerPermission auth.Permission = "worker"
	// List builds and workers, follow events and read logs.
	ReadPermission auth.Permission = auth.Read
	// Cancel any build, reschedule tasks and debug the scheduler.
	AdminPermission auth.Permission = "admin"
)

// Permissions of clients of the scheduler.
var Permissions = []auth.Permission{BuildPermission, WorkerPermission, ReadPermission, AdminPermission}

var grpcPermissions = map[string]auth.Permission{
	protocol.Scheduler_ScheduleBuild_FullMethodName:     BuildPermission,
	protocol.Scheduler_CancelBuild_FullMethodName:       BuildPermission,
	protocol.Scheduler_ScheduleTask_FullMethodName:      BuildPermission,
	protocol.Worker_GetInstructions_FullMethodName:      WorkerPermission,
	protocol.Worker_GetTasks_FullMethodName:             WorkerPermission,
	protocol.Administration_ListBuilds_FullMethodName:   ReadPermission,
	protocol.Administration_ListWorkers_FullMethodName:  ReadPermission,
	protocol.Administration_StreamEvents_FullMethodName: ReadPermission,
	protocol.LogStash_ReadLog_FullMethodName:            ReadPermission,
	protocol.Administration_CancelBuild_FullMethodName:  AdminPermission,
	protocol.Administration_Reschedule_FullMethodName:   AdminPermission,
}

// GrpcPermission returns the permission required to call a gRPC method.
// Unknown methods require administration permission.
func GrpcPermission(method string) auth.Permission {
	if permission, ok := grpcPermissions[method]; ok {
		return permission
	}
	return AdminPermission
}

// HttpPermission returns the permission required for an HTTP request.
func HttpPermission(r *http.Request) auth.Permission {
	if strings.HasPrefix(r.URL.Path, "/debug/") {
		return AdminPermission
	}
	return ReadPermission
}
