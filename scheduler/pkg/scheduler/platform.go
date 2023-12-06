package scheduler

import (
	"bytes"
	"fmt"
	"os"
	"runtime"

	"github.com/denisbrodbeck/machineid"
	"github.com/spf13/viper"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type Platform protocol.Platform

func NewPlatform() *Platform {
	return &Platform{
		Properties: []*protocol.Property{},
	}
}

func NewPlatformWithDefaults() *Platform {
	p := &Platform{
		Properties: []*protocol.Property{},
	}
	p.addDefaults()
	return p
}

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

func (p *Platform) Map() map[string][]string {
	d := map[string][]string{}

	for _, property := range p.Properties {
		d[property.Key] = append(d[property.Key], property.Value)
	}

	return d
}

func (p *Platform) String() string {
	data := bytes.Buffer{}
	for _, prop := range p.Properties {
		fmt.Fprintf(&data, "%s=%s\n", prop.Key, prop.Value)
	}
	return data.String()
}

func (platform *Platform) LoadConfig() error {
	config := viper.Get("platform")
	if config == nil {
		return utils.NotFoundError
	}

	for _, property := range config.([]any) {
		for key, value := range property.(map[string]interface{}) {
			property := &protocol.Property{
				Key:   key,
				Value: value.(string),
			}
			platform.Properties = append(platform.Properties, property)
		}
	}

	return nil
}
