package utils

import (
	"fmt"
	"reflect"
	"strings"

	"github.com/mitchellh/mapstructure"
	"github.com/spf13/viper"
)

func StringToBoolHookFunc() mapstructure.DecodeHookFunc {
	return func(
		f reflect.Type,
		t reflect.Type,
		data interface{},
	) (interface{}, error) {
		if f.Kind() != reflect.String || t.Kind() != reflect.Bool {
			return data, nil
		}

		str := data.(string)
		switch str {
		case "true", "1", "yes":
			return true, nil
		case "false", "0", "no":
			return false, nil
		default:
			return nil, fmt.Errorf("cannot convert %q to bool", str)
		}
	}
}

func StringToIntHookFunc() mapstructure.DecodeHookFunc {
	return func(
		f reflect.Type,
		t reflect.Type,
		data interface{},
	) (interface{}, error) {
		if f.Kind() != reflect.String || t.Kind() != reflect.Int {
			return data, nil
		}

		str := data.(string)
		var i int
		_, err := fmt.Sscanf(str, "%d", &i)
		if err != nil {
			return nil, fmt.Errorf("cannot convert %q to int: %v", str, err)
		}
		return i, nil
	}
}

func StringToStringSliceHookFunc() mapstructure.DecodeHookFunc {
	return func(
		f reflect.Type,
		t reflect.Type,
		data interface{},
	) (interface{}, error) {
		if f.Kind() != reflect.String || t.Kind() != reflect.Slice || t.Elem().Kind() != reflect.String {
			return data, nil
		}

		str := data.(string)
		slice := []string{}
		for _, s := range strings.Split(str, ",") {
			slice = append(slice, strings.TrimSpace(s))
		}
		return slice, nil
	}
}

// Custom unmarshal function to handle time.Duration and bool properly.
func UnmarshalConfig(v viper.Viper, cfg interface{}) error {
	hook := mapstructure.ComposeDecodeHookFunc(
		mapstructure.StringToTimeDurationHookFunc(),
		StringToBoolHookFunc(),
		StringToIntHookFunc(),
		StringToStringSliceHookFunc(),
	)

	decoderConfig := &mapstructure.DecoderConfig{
		DecodeHook: hook,
		Result:     &cfg,
	}

	decoder, _ := mapstructure.NewDecoder(decoderConfig)
	return decoder.Decode(v.AllSettings())
}
