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

func TestPlatformEquals(t *testing.T) {
	a := NewPlatform()
	b := NewPlatform()

	// Empty platforms are equal
	assert.True(t, a.Equals(b))

	// Same properties
	a.AddProperty("node.os", "linux")
	b.AddProperty("node.os", "linux")
	assert.True(t, a.Equals(b))

	// Different number of properties
	a.AddProperty("node.arch", "amd64")
	assert.False(t, a.Equals(b))

	// Same number but different properties
	b.AddProperty("node.arch", "arm64")
	assert.False(t, a.Equals(b))

	// Match again
	b.AddProperty("node.arch", "amd64")
	a.AddProperty("node.arch", "arm64")
	assert.True(t, a.Equals(b))
}
