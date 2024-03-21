package scheduler

import (
	"testing"

	"github.com/spf13/viper"
	"github.com/stretchr/testify/assert"
)

func TestPlatform(t *testing.T) {
	p := NewPlatformWithDefaults()
	r := NewPlatform()

	r.AddProperty("node.arch", "amd64")
	assert.True(t, p.Fulfills(r))

	r.AddProperty("node.os", "linux")
	assert.True(t, p.Fulfills(r))
}

func TestPlatformLoadConfig(t *testing.T) {
	viper.Set("platform", []string{"label=test"})

	p := NewPlatform()
	err := p.LoadConfig()
	assert.NoError(t, err)

	r := NewPlatform()
	r.AddProperty("label", "test")
	assert.True(t, p.Fulfills(r))
}
