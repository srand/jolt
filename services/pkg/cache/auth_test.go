package cache

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/auth"
	"github.com/stretchr/testify/assert"
)

func TestHttpPermission(t *testing.T) {
	for method, permission := range map[string]auth.Permission{
		http.MethodGet:    auth.Read,
		http.MethodHead:   auth.Read,
		http.MethodPost:   auth.Read,
		http.MethodPut:    auth.Write,
		http.MethodDelete: auth.Write,
	} {
		assert.Equal(t, permission, HttpPermission(httptest.NewRequest(method, "/files/a", nil)), method)
	}
}

func TestGrpcPermission(t *testing.T) {
	assert.Equal(t, auth.Read, GrpcPermission(CacheService_HasObject_FullMethodName))
	assert.Equal(t, auth.Read, GrpcPermission(CacheService_HasTree_FullMethodName))
	assert.Equal(t, auth.Read, GrpcPermission(CacheService_ReadObject_FullMethodName))
	assert.Equal(t, auth.Write, GrpcPermission(CacheService_WriteObject_FullMethodName))
}
