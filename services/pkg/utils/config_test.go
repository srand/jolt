package utils

import (
	"testing"
	"time"

	"github.com/spf13/viper"
	"github.com/stretchr/testify/assert"
)

type testConfig struct {
	Enabled  bool          `mapstructure:"enabled"`
	Count    int           `mapstructure:"count"`
	Names    []string      `mapstructure:"names"`
	Timeout  time.Duration `mapstructure:"timeout"`
	Name     string        `mapstructure:"name"`
	Disabled bool          `mapstructure:"disabled"`
}

func TestUnmarshalConfigFromStrings(t *testing.T) {
	// Values from environment variables are strings, whatever the type of
	// the configuration option.
	v := viper.New()
	v.Set("enabled", "yes")
	v.Set("disabled", "0")
	v.Set("count", "42")
	v.Set("names", "a, b ,c")
	v.Set("timeout", "1m30s")
	v.Set("name", "1")

	config := testConfig{}
	assert.NoError(t, UnmarshalConfig(*v, &config))
	assert.Equal(t, testConfig{
		Enabled:  true,
		Disabled: false,
		Count:    42,
		Names:    []string{"a", "b", "c"},
		Timeout:  90 * time.Second,
		Name:     "1",
	}, config)
}

func TestUnmarshalConfigFromTypedValues(t *testing.T) {
	v := viper.New()
	v.Set("enabled", true)
	v.Set("count", 7)
	v.Set("names", []string{"a", "b"})

	config := testConfig{}
	assert.NoError(t, UnmarshalConfig(*v, &config))
	assert.Equal(t, testConfig{Enabled: true, Count: 7, Names: []string{"a", "b"}}, config)
}

func TestUnmarshalConfigInvalidStrings(t *testing.T) {
	for key, value := range map[string]string{"enabled": "maybe", "count": "many"} {
		v := viper.New()
		v.Set(key, value)
		assert.Error(t, UnmarshalConfig(*v, &testConfig{}), key)
	}
}

func TestStringToBoolHook(t *testing.T) {
	v := viper.New()
	for value, want := range map[string]bool{"true": true, "1": true, "yes": true, "false": false, "0": false, "no": false} {
		v.Set("enabled", value)
		config := testConfig{Enabled: !want}
		assert.NoError(t, UnmarshalConfig(*v, &config), value)
		assert.Equal(t, want, config.Enabled, value)
	}
}
