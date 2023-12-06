package utils

import (
	"bytes"
	"crypto/sha1"
	"encoding/hex"
	"io"
)

func Sha1(reader io.Reader) (string, error) {
	sha1 := sha1.New()
	_, err := io.Copy(sha1, reader)
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(sha1.Sum(nil)), nil
}

func Sha1String(data string) (string, error) {
	return Sha1(bytes.NewBufferString(data))
}
