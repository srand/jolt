package utils

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

var sizeRe = regexp.MustCompile(`(0|[1-9][0-9]*) ?([KMGTPE])?B?`)

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
	case "E":
		value *= 1024
		fallthrough
	case "P":
		value *= 1024
		fallthrough
	case "T":
		value *= 1024
		fallthrough
	case "G":
		value *= 1024
		fallthrough
	case "M":
		value *= 1024
		fallthrough
	case "K":
		value *= 1024
	}

	return value, nil
}

func HumanByteSize(byteSize int64) string {
	unitAndPrecision := []struct {
		unit   string
		format string
	}{
		{"B", "%.0f%s"},
		{"KB", "%.0f%s"},
		{"MB", "%.1f%s"},
		{"GB", "%.2f%s"},
		{"TB", "%.2f%s"},
		{"PB", "%.2f%s"},
		{"EB", "%.2f%s"},
	}

	var index = 0
	var size float64 = float64(byteSize)

	for size > 1024 {
		size /= 1024
		index += 1
	}

	return fmt.Sprintf(unitAndPrecision[index].format, size, unitAndPrecision[index].unit)
}
