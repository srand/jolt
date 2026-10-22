package utils

import (
	"fmt"
	"strings"
)

const (
	Blake3Algorithm = HashAlgorithm("blake3")
	Sha1Algorithm   = HashAlgorithm("sha1")
	Sha256Algorithm = HashAlgorithm("sha256")
)

type HashAlgorithm string

// Lower case hex digits, indexed by their value.
const hexDigits = "0123456789abcdef"

// Returns the value of a hex digit of either case, and false if c is not one.
func hexValue(c byte) (byte, bool) {
	switch {
	case c >= '0' && c <= '9':
		return c - '0', true
	case c >= 'a' && c <= 'f':
		return c - 'a' + 10, true
	case c >= 'A' && c <= 'F':
		return c - 'A' + 10, true
	}
	return 0, false
}

// Returns data, an even number of hex digits of either case, in lower case.
//
// The hex string of a digest is used as a file name in the cache. The result
// is built from hexDigits instead of copied from data, so that it consists of
// hex digits only, whatever data contained.
func canonicalHex(data string) (string, error) {
	if len(data) == 0 || len(data)%2 != 0 {
		return "", fmt.Errorf("invalid hex string: %q", data)
	}

	var canonical strings.Builder
	canonical.Grow(len(data))
	for i := 0; i < len(data); i++ {
		value, ok := hexValue(data[i])
		if !ok {
			return "", fmt.Errorf("invalid hex string: %q", data)
		}
		canonical.WriteByte(hexDigits[value])
	}
	return canonical.String(), nil
}

type Digest struct {
	alg HashAlgorithm
	hex string
}

func ParseDigest(digest string) (Digest, error) {
	alg, data, found := strings.Cut(digest, ":")
	if !found {
		data = alg
		alg = "sha1"
	}

	hex, err := canonicalHex(data)
	if err != nil {
		return Digest{}, err
	}
	size := len(hex) / 2

	switch HashAlgorithm(alg) {
	case Blake3Algorithm:
		if size != 32 {
			return Digest{}, fmt.Errorf("invalid length of blake3 hex string: %d", size)
		}
		return NewDigest(Blake3Algorithm, hex), nil
	case Sha1Algorithm:
		if size != 20 {
			return Digest{}, fmt.Errorf("invalid length of sha1 hex string: %d", size)
		}
		return NewDigest(Sha1Algorithm, hex), nil
	case Sha256Algorithm:
		if size != 32 {
			return Digest{}, fmt.Errorf("invalid length of sha256 hex string: %d", size)
		}
		return NewDigest(Sha256Algorithm, hex), nil
	default:
		return Digest{}, fmt.Errorf("invalid hash algorithm: %s", alg)
	}
}

func NewDigest(algorithm HashAlgorithm, hex string) Digest {
	return Digest{alg: algorithm, hex: hex}
}

func (d Digest) Algorithm() HashAlgorithm {
	return d.alg
}

func (d Digest) Hex() string {
	return d.hex
}

// String returns the digest as "algorithm:hex", the form accepted by ParseDigest.
func (d Digest) String() string {
	return string(d.alg) + ":" + d.hex
}
