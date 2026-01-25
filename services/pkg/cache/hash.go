package cache

import (
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"hash"
	"io"

	"github.com/srand/jolt/scheduler/pkg/utils"
)

type hashWriter struct {
	digest utils.Digest
	hash   hash.Hash
	writer WriteCloseDiscarder
	tee    io.Writer
}

func newHashWriter(writer WriteCloseDiscarder, digest utils.Digest) (*hashWriter, error) {
	var hash hash.Hash

	switch digest.Algorithm() {
	case utils.Blake3Algorithm:
		hash = utils.NewBlake3()
	case utils.Sha1Algorithm:
		hash = sha1.New()
	case utils.Sha256Algorithm:
		hash = sha256.New()
	default:
		return nil, fmt.Errorf("%v: unsupported digest algorithm: %s", utils.ErrBadRequest, digest.Algorithm())
	}

	return &hashWriter{
		digest: digest,
		hash:   hash,
		writer: writer,
		tee:    io.MultiWriter(writer, hash),
	}, nil
}

func (w *hashWriter) Write(data []byte) (int, error) {
	return w.tee.Write(data)
}

func (w *hashWriter) Close() error {
	if err := w.writer.Close(); err != nil {
		return err
	}

	hex := hex.EncodeToString(w.hash.Sum(nil))

	if w.digest.Hex() != hex {
		return fmt.Errorf("%v: hash mismatch: expected %s, got %s", utils.ErrBadRequest, w.digest.Hex(), hex)
	}

	return nil
}

func (w *hashWriter) Discard() error {
	return w.writer.Discard()
}
