package cache

import (
	"bytes"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"github.com/stretchr/testify/suite"
)

type TestWriter struct {
	bytes.Buffer
	closed    bool
	discarded bool
}

func (w *TestWriter) Close() error {
	w.closed = true
	return nil
}

func (w *TestWriter) Discard() error {
	w.discarded = true
	return nil
}

type HashTestSuite struct {
	suite.Suite
}

func (suite *HashTestSuite) SetupTest() {
	log.SetLevel(log.TraceLevel)
}

func (s *HashTestSuite) TestSha1() {
	writer, err := newHashWriter(&TestWriter{}, utils.NewDigest(utils.Sha1Algorithm, "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"))
	s.NoError(err)

	n, err := writer.Write([]byte("hello"))
	s.NoError(err)
	s.Equal(5, n)

	err = writer.Close()
	s.NoError(err)
}

func (s *HashTestSuite) TestSha1Mismatch() {
	writer, err := newHashWriter(&TestWriter{}, utils.NewDigest(utils.Sha1Algorithm, "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"))
	s.NoError(err)

	n, err := writer.Write([]byte("hallo"))
	s.NoError(err)
	s.Equal(5, n)

	err = writer.Close()
	s.Error(err)
}

func (s *HashTestSuite) TestSha256() {
	writer, err := newHashWriter(&TestWriter{}, utils.NewDigest(utils.Sha256Algorithm, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"))
	s.NoError(err)

	n, err := writer.Write([]byte("hello"))
	s.NoError(err)
	s.Equal(5, n)

	err = writer.Close()
	s.NoError(err)
}

func (s *HashTestSuite) TestSha256Mismatch() {
	writer, err := newHashWriter(&TestWriter{}, utils.NewDigest(utils.Sha256Algorithm, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"))
	s.NoError(err)

	n, err := writer.Write([]byte("hallo"))
	s.NoError(err)
	s.Equal(5, n)

	err = writer.Close()
	s.Error(err)
}

func (s *HashTestSuite) TestBadAlgo() {
	_, err := newHashWriter(&TestWriter{}, utils.NewDigest("md5", "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"))
	s.ErrorIs(err, utils.ErrBadRequest)
}

func (s *HashTestSuite) TestStoresMatchingContent() {
	data := []byte("hello")
	digest, err := utils.ParseDigest(blake3Digest(data))
	s.NoError(err)

	target := &TestWriter{}
	writer, err := newHashWriter(target, digest)
	s.NoError(err)
	_, err = writer.Write(data)
	s.NoError(err)
	s.NoError(writer.Close())

	s.Equal(data, target.Bytes())
	s.True(target.closed)
	s.False(target.discarded)
}

func (s *HashTestSuite) TestDiscardsMismatchingContent() {
	// Content that doesn't match the digest must not be stored, or clients
	// would download it later as the object with the digest.
	for _, hex := range []string{
		"0000000000000000000000000000000000000000",
		"aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
		"ffffffffffffffffffffffffffffffffffffffff",
	} {
		target := &TestWriter{}
		writer, err := newHashWriter(target, utils.NewDigest(utils.Sha1Algorithm, hex))
		s.NoError(err)
		_, err = writer.Write([]byte("hallo"))
		s.NoError(err)

		s.ErrorIs(writer.Close(), utils.ErrBadRequest, hex)
		s.False(target.closed, hex)
		s.True(target.discarded, hex)
	}
}

func TestHashTestSuite(t *testing.T) {
	suite.Run(t, new(HashTestSuite))
}
