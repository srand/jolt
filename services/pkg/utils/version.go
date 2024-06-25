package utils

import (
	"strconv"
	"strings"
)

// VersionLessThan compares two versions and returns true if a is less than b.
// The version format is major.minor.patch

// Example: 1.0.0 < 1.0.1
// Example: 1.0.0 < 1.1.0
// Example: 1.0.0 < 2.0.0

func VersionLessThan(a, b string) bool {
	// split versions into parts
	aParts := strings.Split(a, ".")
	bParts := strings.Split(b, ".")

	// compare parts one by one
	for i := 0; i < 3; i++ {
		aPart, _ := strconv.Atoi(aParts[i])
		bPart, _ := strconv.Atoi(bParts[i])

		if aPart < bPart {
			return true
		}

		if aPart > bPart {
			return false
		}
	}

	return false
}
