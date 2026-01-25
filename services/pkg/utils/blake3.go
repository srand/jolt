package utils

/*
#cgo CFLAGS: -O3
#cgo LDFLAGS: -lblake3
#include "blake3.h"
*/
import "C"

import (
	"bytes"
	"encoding/hex"
	"hash"
	"io"
	"unsafe"
)

type blake3Hash struct {
	state C.blake3_hasher
}

func NewBlake3() hash.Hash {
	var h blake3Hash
	C.blake3_hasher_init(&h.state)
	return &h
}

func (h *blake3Hash) Write(p []byte) (n int, err error) {
	if len(p) > 0 {
		C.blake3_hasher_update(&h.state, unsafe.Pointer(&p[0]), C.size_t(len(p)))
	}
	return len(p), nil
}

func (h *blake3Hash) Sum(b []byte) []byte {
	var out [32]C.uint8_t
	C.blake3_hasher_finalize(&h.state, (*C.uint8_t)(&out[0]), C.size_t(len(out)))
	return append(b, C.GoBytes(unsafe.Pointer(&out[0]), C.int(len(out)))...)
}

func (h *blake3Hash) Reset() {
	C.blake3_hasher_init(&h.state)
}

func (h *blake3Hash) Size() int {
	return 32
}

func (h *blake3Hash) BlockSize() int {
	return 64
}

func Blake3(reader io.Reader) (string, error) {
	h := NewBlake3()
	_, err := io.Copy(h, reader)
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func Blake3String(data string) (string, error) {
	return Blake3(bytes.NewBufferString(data))
}
