package utils

import "testing"

func TestVersionLessThan(t *testing.T) {
	// Test cases
	testCases := []struct {
		a        string
		b        string
		expected bool
	}{
		{"1.0.0", "1.0.1", true},
		{"1.0.0", "1.1.0", true},
		{"1.0.0", "2.0.0", true},
		{"1.0.1", "1.0.0", false},
		{"1.1.0", "1.0.0", false},
		{"2.0.0", "1.0.0", false},
		{"1.0.0", "1.0.0", false},
	}

	// Run test cases
	for _, tc := range testCases {
		result := VersionLessThan(tc.a, tc.b)
		if result != tc.expected {
			t.Errorf("VersionLessThan(%s, %s) = %t, expected %t", tc.a, tc.b, result, tc.expected)
		}
	}
}
