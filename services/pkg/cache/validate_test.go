package cache

import (
	"testing"

	"buf.build/go/protovalidate"
	"github.com/stretchr/testify/assert"
	"google.golang.org/protobuf/proto"
)

const sha1Digest = "da39a3ee5e6b4b0d3255bfef95601890afd80709"

func TestValidateAcceptsCacheRequests(t *testing.T) {
	tests := map[string]proto.Message{
		"read":          &ReadObjectRequest{Digest: "sha1:" + sha1Digest},
		"has object":    &HasObjectRequest{Digest: []string{sha1Digest}},
		"has no tree":   &HasTreeRequest{},
		"write a chunk": &WriteObjectRequest{Data: []byte("x")},
	}

	for name, message := range tests {
		t.Run(name, func(t *testing.T) {
			assert.NoError(t, protovalidate.Validate(message))
		})
	}
}

func TestValidateRejectsCacheRequests(t *testing.T) {
	tests := map[string]proto.Message{
		"read without digest": &ReadObjectRequest{},
		"has empty object":    &HasObjectRequest{Digest: []string{""}},
		"has empty tree":      &HasTreeRequest{Digest: []string{""}},
	}

	for name, message := range tests {
		t.Run(name, func(t *testing.T) {
			assert.Error(t, protovalidate.Validate(message))
		})
	}
}
