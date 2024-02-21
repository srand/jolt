package utils

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

var sizeRe = regexp.MustCompile(`(0|[1-9][0-9]*) ?([KMGTPE]i?)?B?`)

func ParseSize(size string) (int64, error) {
	size = strings.TrimSpace(size)

	parts := sizeRe.FindStringSubmatch(size)
	if parts == nil {
		return 0, fmt.Errorf("parse error: %v", size)
	}

	value, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil {
		return 0, fmt.Errorf("parse error: %v", size)
	}

	switch parts[2] {
	case "Ei":
		value *= 1024
		fallthrough
	case "Pi":
		value *= 1024
		fallthrough
	case "Ti":
		value *= 1024
		fallthrough
	case "Gi":
		value *= 1024
		fallthrough
	case "Mi":
		value *= 1024
		fallthrough
	case "Ki":
		value *= 1024

	case "E":
		value *= 1000
		fallthrough
	case "P":
		value *= 1000
		fallthrough
	case "T":
		value *= 1000
		fallthrough
	case "G":
		value *= 1000
		fallthrough
	case "M":
		value *= 1000
		fallthrough
	case "K":
		value *= 1000
	}

	return value, nil
}

func HumanByteSize(byteSize int64) string {
	unitAndPrecision := []struct {
		unit   string
		format string
	}{
		{"B", "%.0f%s"},
		{"KiB", "%.0f%s"},
		{"MiB", "%.1f%s"},
		{"GiB", "%.2f%s"},
		{"TiB", "%.2f%s"},
		{"PiB", "%.2f%s"},
		{"EiB", "%.2f%s"},
	}

	var index = 0
	var size float64 = float64(byteSize)

	for size > 1024 {
		size /= 1024
		index += 1
	}

	return fmt.Sprintf(unitAndPrecision[index].format, size, unitAndPrecision[index].unit)
}
