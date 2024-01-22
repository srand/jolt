package scheduler

import (
	"testing"

	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
)

func TestPlatform(t *testing.T) {
	p := NewPlatformWithDefaults()
	r := NewPlatform()

	r.Properties = []*protocol.Property{{Key: "node.arch", Value: "amd64"}}
	assert.True(t, p.Fulfills(r))

	r.Properties = []*protocol.Property{{Key: "node.os", Value: "linux"}}
	assert.True(t, p.Fulfills(r))
}

func TestPlatformLoadConfig(t *testing.T) {
	viper.Set("platform", []string{"label=test"})

	p := NewPlatform()
	err := p.LoadConfig()
	assert.NoError(t, err)

	r := NewPlatform()
	r.Properties = []*protocol.Property{{Key: "label", Value: "test"}}
	assert.True(t, p.Fulfills(r))
}
