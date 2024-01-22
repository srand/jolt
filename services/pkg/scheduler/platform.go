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

type Platform protocol.Platform

func NewPlatform() *Platform {
	return &Platform{
		Properties: []*protocol.Property{},
	}
}

// NewPlatformWithDefaults creates a new platform with default properties
// like the architecture, operating system, number of cpus and a unique id.
func NewPlatformWithDefaults() *Platform {
	p := &Platform{
		Properties: []*protocol.Property{},
	}
	p.addDefaults()
	return p
}

// addDefaults adds default properties like the architecture, operating system,
// number of cpus and a unique id.
func (p *Platform) addDefaults() {
	p.Properties = append(p.Properties, &protocol.Property{
		Key:   "node.arch",
		Value: runtime.GOARCH,
	})
	p.Properties = append(p.Properties, &protocol.Property{
		Key:   "node.os",
		Value: runtime.GOOS,
	})
	p.Properties = append(p.Properties, &protocol.Property{
		Key:   "node.cpus",
		Value: fmt.Sprint(runtime.NumCPU()),
	})
	if id, err := machineid.ProtectedID("jolt-worker"); err == nil {
		p.Properties = append(p.Properties, &protocol.Property{
			Key:   "node.id",
			Value: id,
		})
	}
	if hostname, err := os.Hostname(); err == nil {
		p.Properties = append(p.Properties, &protocol.Property{
			Key:   "worker.hostname",
			Value: hostname,
		})
	}
}

// Fulfills checks if the platform fulfills the given requirement.
// A platform fulfills a requirement if all properties of the requirement
// are also present in the platform.
func (p *Platform) Fulfills(requirement *Platform) bool {
	d := p.Map()

	for _, property := range requirement.Properties {
		list, ok := d[property.Key]
		if !ok {
			return false
		}

		found := false

		for _, value := range list {
			if value == property.Value {
				found = true
				break
			}
		}

		if !found {
			return false
		}
	}

	return true
}

// Map returns a map of all properties of the platform.
func (p *Platform) Map() map[string][]string {
	d := map[string][]string{}

	for _, property := range p.Properties {
		d[property.Key] = append(d[property.Key], property.Value)
	}

	return d
}

// String returns a string representation of the platform.
func (p *Platform) String() string {
	data := bytes.Buffer{}
	for _, prop := range p.Properties {
		fmt.Fprintf(&data, "%s=%s\n", prop.Key, prop.Value)
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

		property := &protocol.Property{
			Key:   strings.TrimSpace(key),
			Value: value,
		}

		platform.Properties = append(platform.Properties, property)
	}

	return nil
}

// GetPropertiesForKey returns all properties for a given key.
// It searches for the key in the platform's map of properties
// and returns the corresponding values as a slice of strings.
func (p *Platform) GetPropertiesForKey(key string) ([]string, bool) {
	properties, ok := p.Map()[key]
	return properties, ok
}
