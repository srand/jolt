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
