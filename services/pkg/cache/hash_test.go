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
}

func (w *TestWriter) Close() error {
	return nil
}

func (w *TestWriter) Discard() error {
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
	s.Error(err)
}

func TestHashTestSuite(t *testing.T) {
	suite.Run(t, new(HashTestSuite))
}
