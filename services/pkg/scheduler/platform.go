package scheduler

import (
	"bytes"
	"fmt"
	"log"
	"os"
	"runtime"
	"strings"

	"github.com/denisbrodbeck/machineid"
	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/protocol"
)

type Platform map[string]struct{}

func NewPlatform() *Platform {
	return &Platform{}
}

func NewPlatformFromProtobuf(platform *protocol.Platform) *Platform {
	if platform == nil {
		return NewPlatform()
	}

	p := NewPlatform()
	for _, property := range platform.Properties {
		p.AddProperty(property.Key, property.Value)
	}
	return p
}

// NewPlatformWithDefaults creates a new platform with default properties
// like the architecture, operating system, number of cpus and a unique id.
func NewPlatformWithDefaults() *Platform {
	p := &Platform{}
	p.addDefaults()
	return p
}

// AddProperty adds a new property to the platform.
func (p *Platform) AddProperty(key, value string) {
	(*p)[key+"="+value] = struct{}{}
}

// addDefaults adds default properties like the architecture, operating system,
// number of cpus and a unique id.
func (p *Platform) addDefaults() {
	p.AddProperty("node.arch", runtime.GOARCH)
	p.AddProperty("node.os", runtime.GOOS)
	p.AddProperty("node.cpus", fmt.Sprint(runtime.NumCPU()))

	if id, err := machineid.ProtectedID("jolt-worker"); err == nil {
		p.AddProperty("node.id", id)
	}

	if hostname, err := os.Hostname(); err == nil {
		p.AddProperty("worker.hostname", hostname)
	}
}

// Fulfills checks if the platform fulfills the given requirement.
// A platform fulfills a requirement if all properties of the requirement
// are also present in the platform.
func (p *Platform) Fulfills(requirement *Platform) bool {
	for property := range *requirement {
		_, ok := (*p)[property]
		if !ok {
			return false
		}
	}

	return true
}

// Get hostname from platform properties.
func (p *Platform) GetHostname() string {
	hostname, _ := p.GetPropertiesForKey("worker.hostname")
	if len(hostname) > 0 {
		return hostname[0]
	}
	return ""
}

// Protobuf returns the platform as a protobuf message.
func (p *Platform) Protobuf() *protocol.Platform {
	platform := &protocol.Platform{}
	for property := range *p {
		key, value, _ := strings.Cut(property, "=")
		platform.Properties = append(platform.Properties, &protocol.Property{
			Key:   key,
			Value: value,
		})
	}
	return platform
}

// String returns a string representation of the platform.
func (p *Platform) String() string {
	data := bytes.Buffer{}
	for property := range *p {
		fmt.Fprintln(&data, property)
	}
	return data.String()
}

// LoadConfig loads the platform config from the viper config.
// The config can be a string, a list of strings or a list of maps.
// The string config (environment variable) is a comma separated
// list of key value pairs. e.g. "key1=value1,key2=value2".
// The list of strings is a list of key value pairs.
// e.g. ["key1=value1", "key2=value2"].
// The list of maps is a list of maps with key value pairs.
func (platform *Platform) LoadConfig() error {
	config := viper.GetStringSlice("platform")

	for _, config := range config {
		// Cut config string in key and value
		// e.g. "key=value" -> ["key", "value"]
		key, value, ok := strings.Cut(config, "=")
		if !ok {
			log.Fatal("Invalid platform property: ", config)
		}

		platform.AddProperty(strings.TrimSpace(key), value)
	}

	return nil
}

// GetPropertiesForKey returns all properties for a given key.
// It searches for the key in the platform's map of properties
// and returns the corresponding values as a slice of strings.
func (p *Platform) GetPropertiesForKey(key string) ([]string, bool) {
	result := []string{}

	for property := range *p {
		if strings.HasPrefix(property, key+"=") {
			result = append(result, strings.TrimPrefix(property, key+"="))
		}
	}

	if len(result) > 0 {
		return result, true
	}

	return nil, false
}
