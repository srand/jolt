package utils

import (
	"fmt"
	"reflect"

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

// Custom unmarshal function to handle time.Duration and bool properly.
func UnmarshalConfig(v viper.Viper, cfg interface{}) error {
	hook := mapstructure.ComposeDecodeHookFunc(
		mapstructure.StringToTimeDurationHookFunc(),
		StringToBoolHookFunc(),
	)

	decoderConfig := &mapstructure.DecoderConfig{
		DecodeHook: hook,
		Result:     &cfg,
	}

	decoder, _ := mapstructure.NewDecoder(decoderConfig)
	return decoder.Decode(v.AllSettings())
}
