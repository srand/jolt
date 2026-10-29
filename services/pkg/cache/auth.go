package cache

import (
	"net/http"

	"github.com/srand/jolt/scheduler/pkg/auth"
)

// Permissions of clients of the cache.
var Permissions = []auth.Permission{auth.Read, auth.Write}

// HttpPermission returns the permission required for an HTTP request.
// Objects and files are written with PUT. POST only looks them up.
func HttpPermission(r *http.Request) auth.Permission {
	switch r.Method {
	case http.MethodGet, http.MethodHead, http.MethodPost:
		return auth.Read
	}
	return auth.Write
}

// GrpcPermission returns the permission required to call a gRPC method.
func GrpcPermission(method string) auth.Permission {
	if method == CacheService_WriteObject_FullMethodName {
		return auth.Write
	}
	return auth.Read
}
