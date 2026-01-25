package utils

import (
	"encoding/hex"
	"fmt"
	"strings"
)

const (
	Blake3Algorithm = HashAlgorithm("blake3")
	Sha1Algorithm   = HashAlgorithm("sha1")
	Sha256Algorithm = HashAlgorithm("sha256")
)

type HashAlgorithm string

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

	bytes, err := hex.DecodeString(data)
	if err != nil {
		return Digest{}, err
	}

	switch HashAlgorithm(alg) {
	case Blake3Algorithm:
		if len(bytes) != 32 {
			return Digest{}, fmt.Errorf("invalid length of blake3 hex string: %d", len(bytes))
		}
		return NewDigest(Blake3Algorithm, data), nil
	case Sha1Algorithm:
		if len(bytes) != 20 {
			return Digest{}, fmt.Errorf("invalid length of sha1 hex string: %d", len(bytes))
		}
		return NewDigest(Sha1Algorithm, data), nil
	case Sha256Algorithm:
		if len(bytes) != 32 {
			return Digest{}, fmt.Errorf("invalid length of sha256 hex string: %d", len(bytes))
		}
		return NewDigest(Sha256Algorithm, data), nil
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
