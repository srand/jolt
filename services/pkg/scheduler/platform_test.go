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

func TestPlatformFulfills(t *testing.T) {
	p := NewPlatform()
	p.AddProperty("node.os", "linux")
	p.AddProperty("label", "fast")

	r := NewPlatform()
	assert.True(t, p.Fulfills(r), "no requirements")

	r.AddProperty("node.os", "linux")
	assert.True(t, p.Fulfills(r))

	r.AddProperty("label", "slow")
	assert.False(t, p.Fulfills(r), "missing property")

	other := NewPlatform()
	other.AddProperty("node.os", "windows")
	assert.False(t, p.Fulfills(other), "other value of property")
}

func TestPlatformEqualsSubset(t *testing.T) {
	a := NewPlatform()
	a.AddProperty("node.os", "linux")
	b := NewPlatform()
	b.AddProperty("node.os", "linux")
	b.AddProperty("node.arch", "amd64")

	assert.False(t, a.Equals(b))
	assert.False(t, b.Equals(a))
}

func TestPlatformProtobufRoundTrip(t *testing.T) {
	p := NewPlatform()
	p.AddProperty("node.os", "linux")
	p.AddProperty("label", "a=b")

	assert.True(t, p.Equals(NewPlatformFromProtobuf(p.Protobuf())))
	assert.True(t, NewPlatform().Equals(NewPlatformFromProtobuf(nil)))
}

func TestPlatformGetPropertiesForKey(t *testing.T) {
	p := NewPlatform()
	p.AddProperty("label", "fast")
	p.AddProperty("label", "linux")
	p.AddProperty("labels", "other")

	labels, ok := p.GetPropertiesForKey("label")
	assert.True(t, ok)
	assert.ElementsMatch(t, []string{"fast", "linux"}, labels)

	values, ok := p.GetPropertiesForKey("missing")
	assert.False(t, ok)
	assert.Empty(t, values)
}

func TestPlatformGetHostname(t *testing.T) {
	p := NewPlatform()
	assert.Equal(t, "", p.GetHostname())

	p.AddProperty("worker.hostname", "host")
	assert.Equal(t, "host", p.GetHostname())
}
