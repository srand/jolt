package utils

import (
	"crypto/rand"
	"encoding/hex"
	"testing"
)

func TestBlake3BasicFunctionality(t *testing.T) {
	h := NewBlake3()

	// Test Size and BlockSize
	if h.Size() != 32 {
		t.Errorf("Expected Size() to return 32, got %d", h.Size())
	}

	if h.BlockSize() != 64 {
		t.Errorf("Expected BlockSize() to return 64, got %d", h.BlockSize())
	}
}

func TestBlake3EmptyInput(t *testing.T) {
	h := NewBlake3()
	result := h.Sum(nil)

	// Blake3 hash of empty input is known
	expected := "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"
	actual := hex.EncodeToString(result)

	if actual != expected {
		t.Errorf("Hash of empty input doesn't match expected.\nExpected: %s\nActual:   %s", expected, actual)
	}
}

func TestBlake3KnownInputs(t *testing.T) {
	testCases := []struct {
		input    string
		expected string
	}{
		{
			input:    "hello world",
			expected: "d74981efa70a0c880b8d8c1985d075dbcbf679b99a5f9914e5aaf96b831a9e24",
		},
		{
			input:    "The quick brown fox jumps over the lazy dog",
			expected: "2f1514181aadccd913abd94cfa592701a5686ab23f8df1dff1b74710febc6d4a",
		},
	}

	for _, tc := range testCases {
		h := NewBlake3()
		h.Write([]byte(tc.input))
		result := h.Sum(nil)
		actual := hex.EncodeToString(result)

		if actual != tc.expected {
			t.Errorf("Hash of '%s' doesn't match expected.\nExpected: %s\nActual:   %s",
				tc.input, tc.expected, actual)
		}
	}
}

func TestBlake3Write(t *testing.T) {
	h := NewBlake3()

	// Test writing data in chunks
	input := []byte("hello world")
	n, err := h.Write(input)

	if err != nil {
		t.Errorf("Write() returned error: %v", err)
	}

	if n != len(input) {
		t.Errorf("Write() returned %d bytes written, expected %d", n, len(input))
	}

	// Verify the hash is correct
	result := h.Sum(nil)
	expected := "d74981efa70a0c880b8d8c1985d075dbcbf679b99a5f9914e5aaf96b831a9e24"
	actual := hex.EncodeToString(result)

	if actual != expected {
		t.Errorf("Hash doesn't match expected after Write().\nExpected: %s\nActual:   %s", expected, actual)
	}
}

func TestBlake3MultipleWrites(t *testing.T) {
	h1 := NewBlake3()
	h2 := NewBlake3()

	// Write data in one go
	fullData := []byte("hello world")
	h1.Write(fullData)
	result1 := h1.Sum(nil)

	// Write data in chunks
	h2.Write([]byte("hello "))
	h2.Write([]byte("world"))
	result2 := h2.Sum(nil)

	if hex.EncodeToString(result1) != hex.EncodeToString(result2) {
		t.Errorf("Results differ when writing data in chunks vs all at once.\nSingle write: %s\nChunked write: %s",
			hex.EncodeToString(result1), hex.EncodeToString(result2))
	}
}

func TestBlake3Reset(t *testing.T) {
	h := NewBlake3()

	// Write some data
	h.Write([]byte("some data"))

	// Reset the hasher
	h.Reset()

	// Should now behave as if it's a fresh hasher
	result := h.Sum(nil)
	expected := "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262" // empty hash
	actual := hex.EncodeToString(result)

	if actual != expected {
		t.Errorf("Reset() didn't properly reset the hasher.\nExpected: %s\nActual:   %s", expected, actual)
	}
}

func TestBlake3SumWithExistingSlice(t *testing.T) {
	h := NewBlake3()
	h.Write([]byte("test"))

	// Test Sum() with existing slice
	existing := []byte{0x01, 0x02, 0x03}
	result := h.Sum(existing)

	// Result should have original bytes plus hash
	if len(result) != len(existing)+32 {
		t.Errorf("Sum() result length incorrect. Expected %d, got %d", len(existing)+32, len(result))
	}

	// Check that original bytes are preserved
	for i, b := range existing {
		if result[i] != b {
			t.Errorf("Sum() didn't preserve existing slice bytes at position %d", i)
		}
	}
}

func TestBlake3LargeInput(t *testing.T) {
	h := NewBlake3()

	// Create a large input (1MB of random data)
	largeInput := make([]byte, 1024*1024)
	if _, err := rand.Read(largeInput); err != nil {
		t.Fatalf("Failed to generate random data: %v", err)
	}

	// Write the large input
	n, err := h.Write(largeInput)
	if err != nil {
		t.Errorf("Write() failed for large input: %v", err)
	}

	if n != len(largeInput) {
		t.Errorf("Write() didn't write all bytes for large input. Expected %d, got %d", len(largeInput), n)
	}

	// Verify we get a hash result
	result := h.Sum(nil)
	if len(result) != 32 {
		t.Errorf("Sum() result length incorrect for large input. Expected 32, got %d", len(result))
	}
}

func BenchmarkBlake3Small(b *testing.B) {
	data := []byte("hello world")

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		h := NewBlake3()
		h.Write(data)
		h.Sum(nil)
	}
}

func BenchmarkBlake31KB(b *testing.B) {
	data := make([]byte, 1024)
	rand.Read(data)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		h := NewBlake3()
		h.Write(data)
		h.Sum(nil)
	}
}
